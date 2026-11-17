"""Assess a saved report with Qwen without repeating search or synthesis."""
import argparse
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path

from app.agent import API_KEY, BASE_URL, MODEL, call_model
from app.verification.node import make_claim_verification_node
from app.workflow.artifacts import RunArtifacts, utc_now
from app.workflow.nodes import validate_report_node

ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger("app.workflow.verification")


async def verify_saved_report(input_run: Path, output_dir: Path = ROOT / "runs",
                              max_model_calls: int = 8, model_call=call_model) -> dict:
    if max_model_calls < 1:
        raise ValueError("max_model_calls must be positive.")
    raw = (Path(input_run) / "result.json").read_bytes()
    saved = json.loads(raw)
    if "report" not in saved:
        raise ValueError("The saved run has no final report to verify.")
    artifacts = RunArtifacts(output_dir, secrets=(API_KEY, os.getenv("TAVILY_API_KEY", "")))
    metadata = {"run_id": artifacts.run_id, "module": "claim_verification",
                "input_run": str(Path(input_run).resolve()),
                "input_result_hash": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "started_at": utc_now(), "status": "running", "model": MODEL,
                "endpoint": BASE_URL, "max_model_calls": max_model_calls,
                "model_provider": "qwen" if model_call is call_model else "test_callable"}
    artifacts.write_json("run.json", metadata)
    with artifacts.capture_logs():
        logger.info("Verifying saved report: %s; output: %s", input_run, artifacts.directory)
        state = {"latest_reply": {"content": json.dumps(saved["report"])},
                 "trace": saved.get("trace", []), "model_count": 0,
                 "max_model_calls": max_model_calls, "verify_claims": True}
        try:
            state.update(validate_report_node(state))
            if state["status"] == "answered":
                state.update(await make_claim_verification_node(artifacts.record_model(model_call))(state))
            result = {**state["result"], "model_calls": state["model_count"], "tool_calls": 0,
                      "trace": state["trace"], "sources": saved.get("sources", {}),
                      "source_run_id": saved.get("run_id"), "run_id": artifacts.run_id,
                      "artifacts_dir": str(artifacts.directory)}
        except Exception as exc:
            logger.exception("Saved-report verification failed.")
            result = {"status": "failed", "reason": "saved_verification_failed", "error": str(exc),
                      "run_id": artifacts.run_id, "artifacts_dir": str(artifacts.directory),
                      "model_calls": artifacts.model_calls}
        artifacts.write_json("result.json", result)
        artifacts.write_json("trace.json", saved.get("trace", []))
        if "claim_verification" in result:
            artifacts.write_json("claim_verification.json", result["claim_verification"])
        metadata.update(status=result["status"], finished_at=utc_now(), model_calls=result["model_calls"])
        artifacts.write_json("run.json", metadata)
        logger.info("Saved verification finished: %s; records: %s", result["status"], artifacts.directory)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "runs")
    parser.add_argument("--max-model-calls", type=int, default=8)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
    outcome = asyncio.run(verify_saved_report(args.input_run, args.output_dir, args.max_model_calls))
    print(json.dumps(outcome, indent=2))
