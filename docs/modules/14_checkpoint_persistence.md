# 14 — Persistent checkpoints and process restart recovery

## What changed

The graph can now resume pending work after the Python process exits. The normal `python -m app.workflow.runner` command uses a local SQLite LangGraph checkpointer by default. Existing `run_graph_agent()` and `run_saved_research()` APIs remain available without persistence for isolated checks; `run_checkpointed_research()` is the persistent entry point.

Run logs explain what happened. Checkpoints restore execution. These are complementary records, not interchangeable files.

## Architecture

```text
CLI → immutable session configuration + exclusive run lock
    → AsyncSqliteSaver + thread_id
    → compile existing graph with checkpointer
    → invoke initial state, saving graph state at node boundaries

Pause/process exit
    → new process reads same session and SQLite database
    → new MCP server loads source registry and cached source text
    → rebuild same graph with same thread_id
    → inspect saved state and pending nodes
    → invoke(None) to continue pending work
```

The graph uses synchronous checkpoint durability (`durability="sync"`): a checkpoint write completes before the next graph step begins. Completed nodes do not ordinarily run again on resume. An unfinished node can run again, so model/tool request replay and source persistence are handled separately.

## Files

| File | Responsibility |
|---|---|
| `app/workflow/persistent.py` | Session lifecycle, SQLite saver, thread identity, single-writer lock, request journal and state inspection |
| `app/workflow/graph.py` | Compile with optional checkpointer, static pause points and journalled tool executor |
| `app/workflow/runner.py` | CLI start/resume/inspect, `ainvoke(None)` and paused outcomes |
| `app/workflow/artifacts.py` | Reopen an existing run and append progress/model records |
| `app/retrieval/web.py` | Persist and restore discovered sources, cached reads and search results |
| `app/retrieval/settings.py` | Serialize actual configured retrieval values for the MCP child |
| `app/mcp_server.py` | Open the source store specified by the trusted host |
| `checks/check_persistence.py` | Separate-process recovery, replay limits, cache integrity and locking tests |
| `checks/checkpoint_worker.py` | Simulated-model process fixture, including deliberate hard exit |

Install the added dependency with `python -m pip install -r requirements.txt`. The implementation uses `langgraph-checkpoint-sqlite>=3,<4` and its async SQLite support. No PostgreSQL service is required.

## LangGraph concepts

**Checkpointer:** `AsyncSqliteSaver` stores graph snapshots, channel values, execution metadata and pending work in `checkpoints.sqlite`.

**Thread identity:** `config={"configurable": {"thread_id": ...}}` selects one execution's checkpoint history. We use the unique run ID. Resuming does not create a new thread or append the original question again.

**State inspection:** `aget_state()` shows current values and `.next` pending nodes. `aget_state_history()` shows prior snapshots. Our CLI prints checkpoint IDs, times, counters, status and pending nodes without dumping all source text.

**Static pause:** `interrupt_after=["tools"]` or another supported node pauses at a completed node boundary. Resume with `ainvoke(None, config)`. This module uses static breakpoints, not dynamic human-approval `interrupt()`/`Command(resume=...)` behavior.

**Checkpoint versus retry:** restoring a snapshot resumes pending work; it does not automatically reopen a workflow that already reached a terminal handled failure. A completed thread returns its existing outcome without making new model/tool requests. Inspect the checkpoint before assuming it has work to resume.

## Commands

```bash
# Normal research now has persistent checkpoints:
python -m app.workflow.runner --backend web \
  --question "What are Python generators?"

# Deliberately pause after the first tool node:
python -m app.workflow.runner --backend web --pause-after tools \
  --question "What are Python generators?"

# Inspect an existing persistent run; no model request:
python -m app.workflow.runner --inspect runs/<run-id>

# Resume in a new process, using the original question and budgets:
python -m app.workflow.runner --resume runs/<run-id>

# Optional second boundary for learning: pause after task assessment:
python -m app.workflow.runner --resume runs/<run-id> --pause-after assess

# Controlled checks; no Qwen or external web requests:
python -m checks.check_persistence
```

Pause choices are `planner`, `tools`, and `assess`. A supplied pause applies whenever that node executes in that invocation; omit it to finish the remaining work. The same run directory receives appended logs and new attempt records. Normal result JSON includes `thread_id`, `checkpoint_id`, `resumable`, and cumulative counters.

The saved session owns the original budgets, backend/provider, allowed domains, retrieval limits, verification and follow-up settings. Resume does not reset or increase them; new budget flags do not override the saved values. The configured Qwen model/endpoint must match. Credentials remain in the environment and are not copied into session configuration.

## MCP source restoration

The MCP server is a new process after restart. SQLite graph state alone does not restore its memory. The host explicitly passes a run-local `sources.json` path through `RESEARCH_SOURCE_STATE`.

Sources and successful read text are saved atomically before returning success to the graph. Search results are cached within that run as well. On restart, source IDs are checked against canonical approved URL hashes and cached text against its stored content hash. Missing required source state or invalid cached state blocks safe continuation instead of inventing a replacement ID/text version.

Repeated reads return the saved text, keeping quotations consistent across resumes even if the live page has changed. This is a run snapshot, not a guarantee that the evidence remains current. Local fictional documents are deterministic and do not need a separate web-source file.

## Request replay and budgets

`requests.json` records started attempts and completed model/tool results. Identical completed inputs can reuse a recorded result after replay, including an interrupted node that had already completed an external call. It is per-run memoization, not a shared/global model cache.

An unfinished recorded request is uncertain: the remote service may already have processed it. A retry consumes another attempt. The implementation does not claim exactly-once remote execution or billing. Tools are read-only; irreversible actions would need their own idempotency strategy.

Two counters are intentionally exposed:

- `model_calls` / `tool_calls`: logical graph counters restored from checkpoints. These include controller cache reuse where applicable.
- `actual_model_attempts` / `actual_tool_attempts`: journalled starts that survive even if a node does not finish. They conservatively count uncertain attempts and are independently capped by the original session budgets. A tool attempt is an MCP invocation, not an individual HTTP request or redirect.

A hard-crash test demonstrates seven completed logical model calls and eight recorded attempts because one attempt was interrupted. Budgets do not restart from zero. A completed cached request does not make a new remote call. Attempt-limit refusals remain explicit errors; checkpointing is not a new unlimited retry policy.

## Saved records

```text
runs/<run-id>/
├── session.json          # Original configuration, thread ID and source-code fingerprint
├── checkpoints.sqlite    # LangGraph snapshots and pending execution
├── sources.json          # Web source registry, search cache and successful reads
├── requests.json         # Model/tool attempts and completed response replay
├── attempts/0001.json    # First invocation outcome
├── attempts/0002.json    # Resume outcome; earlier invocation remains available
├── run.json              # Latest status and cumulative counters
├── result.json           # Latest paused/final outcome
├── run.log               # Appended progress across invocations
├── model_calls.jsonl     # Appended actual model request/response/error records
└── ...                   # Existing trace, follow-up and verification records
```

Keep the entire run directory, including SQLite sidecar files if present after an abrupt exit. Archives contain workflow text and are trusted local data, not encrypted storage. Credentials are not intentionally stored as configuration; user-supplied/source/model text is retained. The `runs/` folder remains ignored by Git.

## Guardrails and limitations

- An exclusive local file lock prevents two processes from writing the same run concurrently. The current implementation targets Linux/POSIX.
- A fingerprint of the Python application files prevents silently resuming with changed workflow code. Restore the original code/environment rather than editing checkpoint data; migrations are not implemented.
- Older JSON-only runs lack checkpoints and cannot be resumed retroactively.
- SQLite is appropriate for this local portfolio workflow, not a claim of distributed production reliability.
- A crash before the first durable checkpoint may require a new run. Disk failure, missing files or corrupted state are not automatically repaired.
- Handled terminal failures remain terminal. Recovery covers pending nodes after interruption/unexpected failure, not every possible endpoint outage.
- Requests and graph checkpoints are separate transactions; exactly-once execution is not guaranteed. Started attempts are nevertheless retained and capped. Restart only after the original process has exited; cancellation of a blocking HTTP worker is not instantaneous.
- Source text and checkpoint histories consume storage; no automatic archival/cleanup or checkpoint migration is provided.

## Verification and interview questions

Six deterministic tests passed, including a real `os._exit` in a separate process, pause/exit/resume, no replay of completed work, terminal-run idempotence, changed-code refusal, source restoration and hash integrity, attempt caps and the single-writer lock. All 24 check modules passed.

**Why not just save the final report?** A report does not contain the graph's pending execution position or all channel updates needed to continue.

**Is thread state the same as long-term agent memory?** No. This is persistence for one research execution, not a cross-user knowledge store.

**Why save MCP sources separately?** The tool server's registry lives outside LangGraph state and must survive its own process restart.

**Can an interrupted node run twice?** Yes. Completed result replay reduces duplicate calls, but an uncertain in-flight call can be retried. Irreversible operations need stronger idempotency controls.


## Live acceptance run

Thread `20261117T111447_278790Z_71698170` was started with Qwen, paused after search, resumed in another process through source reading/task assessment, then resumed again to completion. Counters progressed **2/1 → 6/3 → 13/6** (graph model/tool calls), with the original **40/25 limits** preserved. The final report contained **three claims assessed supported** and disclosed remaining gaps.

The request journal recorded **11 model attempts and two MCP invocations**, since completed model/tool results were reused. A fourth invocation of the already finished thread made no new attempts. Both source restoration and skipping completed task one were visible in `run.log`. Per-invocation outcomes, source integrity, citations and cumulative counters were checked from saved records.

Inspect `runs/20261117T111447_278790Z_71698170/validation.md`, `checkpoint_history.json` and `attempts/` locally. Follow-up was disabled specifically for this recovery demonstration; semantic verification remained enabled. This example and the hard-exit tests demonstrate the stated local recovery behavior, not general production reliability.
