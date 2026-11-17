"""SQLite checkpoint lifecycle, source restoration, and bounded request replay."""
import asyncio
import fcntl
import hashlib
import json
import logging
import os
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agent import API_KEY, BASE_URL, MODEL, call_model
from app.mcp_tools import execute_mcp_tool
from app.retrieval.settings import RetrievalSettings
from app.workflow.artifacts import RunArtifacts, utc_now
from app.workflow.graph import build_research_graph
from app.workflow.runner import PROJECT_ROOT, run_graph_agent

logger = logging.getLogger("app.workflow.persistence")


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def code_fingerprint():
    digest = hashlib.sha256()
    for path in sorted((PROJECT_ROOT / "app").rglob("*.py")):
        digest.update(str(path.relative_to(PROJECT_ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


@contextmanager
def exclusive_run(directory):
    with (directory / ".run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("This run is already active in another process.") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


class RequestJournal:
    """Completed identical requests are reusable; uncertain attempts still consume budget."""
    def __init__(self, directory, model_limit, tool_limit):
        self.path = directory / "requests.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {
            "model_attempts": 0, "tool_attempts": 0, "models": {}, "tools": {}}
        self.model_limit, self.tool_limit = model_limit, tool_limit

    def save(self):
        atomic_json(self.path, self.data)

    def key(self, value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def model(self, function):
        def invoke(messages, tools):
            key = self.key([messages, tools])
            entry = self.data["models"].get(key, {})
            if entry.get("status") == "complete":
                logger.info("Replaying recorded model response; no Qwen request.")
                return entry["result"]
            if self.data["model_attempts"] >= self.model_limit:
                raise ValueError("Persistent model attempt limit reached.")
            self.data["model_attempts"] += 1
            self.data["models"][key] = {"status": "pending", "at": utc_now()}
            self.save()
            # An exception/crash leaves a pending entry. A retry consumes another attempt.
            result = function(messages, tools)
            self.data["models"][key] = {"status": "complete", "result": result}
            self.save()
            return result
        return invoke

    async def tool(self, client, name, arguments):
        key = self.key([name, json.loads(arguments)])
        entry = self.data["tools"].get(key, {})
        if entry.get("status") == "complete":
            logger.info("Replaying recorded %s result; no MCP invocation.", name)
            return entry["result"]
        if self.data["tool_attempts"] >= self.tool_limit:
            return {"error": "persistent_tool_attempt_limit_reached"}
        self.data["tool_attempts"] += 1
        self.data["tools"][key] = {"status": "pending", "at": utc_now()}
        self.save()
        result = await execute_mcp_tool(client, name, arguments)
        if "error" not in result:
            self.data["tools"][key] = {"status": "complete", "result": result}
            self.save()
        return result


async def inspect_checkpoints(directory: Path, limit=10):
    manifest = json.loads((directory / "session.json").read_text())
    if not (directory / "checkpoints.sqlite").exists():
        raise ValueError("Checkpoint database is missing.")
    async with AsyncSqliteSaver.from_conn_string(str(directory / "checkpoints.sqlite")) as saver:
        graph = build_research_graph(None, [], call_model, checkpointer=saver)
        config = {"configurable": {"thread_id": manifest["thread_id"]}}
        snapshots = []
        async for snapshot in graph.aget_state_history(config, limit=limit):
            snapshots.append({"checkpoint_id": snapshot.config["configurable"].get("checkpoint_id"),
                "created_at": snapshot.created_at, "next": list(snapshot.next),
                "model_calls": snapshot.values.get("model_count", 0),
                "tool_calls": snapshot.values.get("tool_count", 0), "status": snapshot.values.get("status")})
        return {"thread_id": manifest["thread_id"], "snapshots": snapshots}


async def run_checkpointed_research(question=None, max_model_calls=60, max_tool_calls=60,
        research_backend=None, verify_claims=True, max_followup_cycles=1,
        output_dir=PROJECT_ROOT / "runs", resume_dir=None, pause_after=None, model_call=call_model):
    secrets = (API_KEY, os.getenv("TAVILY_API_KEY", ""))
    if resume_dir:
        directory = Path(resume_dir).resolve()
        if not (directory / "session.json").exists():
            raise ValueError("No persistent session found; older JSON-only runs cannot be resumed.")
        artifacts = RunArtifacts.reopen(directory, secrets)
    else:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("A nonempty research question is required.")
        if max_model_calls < 1 or max_tool_calls < 0 or max_followup_cycles not in (0, 1):
            raise ValueError("Invalid research budgets or follow-up limit.")
        artifacts = RunArtifacts(Path(output_dir), secrets)
        directory = artifacts.directory.resolve()
    with exclusive_run(directory):
        if resume_dir:
            manifest = json.loads((directory / "session.json").read_text())
            if manifest.get("version") != 1 or manifest["code_fingerprint"] != code_fingerprint():
                raise ValueError("Code/session version changed; use the original code to resume this run.")
            if manifest["configured_model"] != MODEL or manifest["endpoint"] != BASE_URL:
                raise ValueError("Qwen configuration changed; restore the original model and endpoint.")
            if not (directory / "checkpoints.sqlite").exists():
                raise ValueError("Cannot resume without the checkpoint database.")
            saved_settings = dict(manifest["retrieval"])
            saved_settings["allowed_domains"] = tuple(saved_settings["allowed_domains"])
            settings = RetrievalSettings(**saved_settings, tavily_api_key=os.getenv("TAVILY_API_KEY", ""))
            if settings.provider == "tavily" and not settings.tavily_api_key:
                raise ValueError("Restore TAVILY_API_KEY to resume Tavily retrieval.")
        else:
            settings = RetrievalSettings.from_env(research_backend)
            retrieval = asdict(settings); retrieval.pop("tavily_api_key")
            manifest = {"version": 1, "thread_id": artifacts.run_id, "question": question,
                "model": MODEL if model_call is call_model else "simulated", "configured_model": MODEL,
                "model_provider": "qwen" if model_call is call_model else "test_callable",
                "endpoint": BASE_URL, "code_fingerprint": code_fingerprint(),
                "retrieval": retrieval, "max_model_calls": max_model_calls,
                "max_tool_calls": max_tool_calls, "verify_claims": verify_claims,
                "max_followup_cycles": max_followup_cycles, "started_at": utc_now()}
            artifacts.write_json("session.json", manifest)
        journal = RequestJournal(directory, manifest["max_model_calls"], manifest["max_tool_calls"])
        artifacts.model_calls = journal.data["model_attempts"]
        attempts_dir = directory / "attempts"; attempts_dir.mkdir(exist_ok=True)
        attempt_file = attempts_dir / f"{len(list(attempts_dir.glob('*.json'))) + 1:04d}.json"
        attempt = {"started_at": utc_now(), "resume": bool(resume_dir), "status": "running"}
        atomic_json(attempt_file, attempt)
        with artifacts.capture_logs():
            logger.info("%s persistent thread %s; records: %s", "Resuming" if resume_dir else "Starting", manifest["thread_id"], directory)
            async with AsyncSqliteSaver.from_conn_string(str(directory / "checkpoints.sqlite")) as saver:
                config = {"configurable": {"thread_id": manifest["thread_id"]}}
                prior = await saver.aget_tuple(config)
                if resume_dir and not prior:
                    raise ValueError("No durable checkpoint exists for this thread.")
                if resume_dir and settings.backend == "web" and not (directory / "sources.json").exists():
                    if prior.checkpoint.get("channel_values", {}).get("trace"):
                        raise ValueError("The source store is missing; restore sources.json before resuming.")
                try:
                    result = await run_graph_agent(manifest["question"],
                        max_model_calls=manifest["max_model_calls"], max_tool_calls=manifest["max_tool_calls"],
                        research_backend=settings.backend, retrieval_settings=settings,
                        verify_claims=manifest["verify_claims"], max_followup_cycles=manifest["max_followup_cycles"],
                        model_call=journal.model(artifacts.record_model(model_call)),
                        tool_executor=journal.tool, checkpointer=saver, thread_id=manifest["thread_id"],
                        resume=bool(resume_dir), interrupt_after=[pause_after] if pause_after else None,
                        source_state_path=directory / "sources.json")
                except (Exception, asyncio.CancelledError) as exc:
                    logger.warning("Persistent execution interrupted (%s); inspecting checkpoint.", type(exc).__name__)
                    graph = build_research_graph(None, [], model_call, checkpointer=saver)
                    snapshot = await graph.aget_state(config)
                    result = {"status": "paused" if snapshot.next else "failed", "reason": "execution_interrupted",
                              "error": str(exc), "pending_nodes": list(snapshot.next),
                              "model_calls": snapshot.values.get("model_count", 0),
                              "tool_calls": snapshot.values.get("tool_count", 0),
                              "trace": snapshot.values.get("trace", []),
                              "tasks": snapshot.values.get("tasks", []),
                              "task_results": snapshot.values.get("task_results", {})}
                snapshot = await build_research_graph(None, [], model_call, checkpointer=saver).aget_state(config)
                result.update(resumable=bool(snapshot.next), thread_id=manifest["thread_id"],
                              checkpoint_id=snapshot.config["configurable"].get("checkpoint_id") if snapshot.config else None)
            result.update(run_id=manifest["thread_id"], artifacts_dir=str(directory),
                          actual_model_attempts=journal.data["model_attempts"],
                          actual_tool_attempts=journal.data["tool_attempts"])
            for name, value in (("result.json", result), ("trace.json", result.get("trace", [])),
                    ("followup.json", {"cycles_used": result.get("followup_count", 0),
                        "decision": result.get("followup_decision", {}), "history": result.get("followup_history", [])})):
                artifacts.write_json(name, value)
            if "claim_verification" in result:
                artifacts.write_json("claim_verification.json", result["claim_verification"])
            attempt.update(finished_at=utc_now(), status=result["status"], result=result)
            atomic_json(attempt_file, attempt)
            artifacts.write_json("run.json", {**manifest, "status": result["status"], "updated_at": utc_now(),
                "model_calls": result["model_calls"], "tool_calls": result["tool_calls"],
                "resumable": result["resumable"], "actual_model_attempts": journal.data["model_attempts"],
                "actual_tool_attempts": journal.data["tool_attempts"]})
            logger.info("Persistent execution: %s; resumable=%s; records: %s", result["status"], result["resumable"], directory)
        return result
