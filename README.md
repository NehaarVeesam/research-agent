# Research Agent

A learning-focused research agent built with Python, Qwen, MCP, and LangGraph. It investigates a small fictional document collection and produces structured findings with source IDs, exact quotes, evidence gaps, and an execution trace.

**Current milestone:** both a manual Python-loop controller and a LangGraph workflow are implemented. External web research, semantic claim verification, and persistence are future work.

## How it works

```text
Question → Qwen → Tool requests → MCP server → Search/read documents
              ↑                                      |
              └──────── Tool observations ────────────┘
              |
              └── Final JSON → Schema + source/quote checks → Result
```

The model chooses actions. Application code enforces tool permissions and call limits. MCP provides tool discovery and invocation; LangGraph organizes state, nodes, and routing. The local stdio server starts automatically for each run, with no HTTP port required.

## Setup

Use Python 3.11+ and run commands from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

If you do not already have `.env`, create it from the template:

```bash
cp .env.example .env
```

Set your endpoint and exact served model identifier:

```dotenv
QWEN_BASE_URL=http://localhost:8100/v1
QWEN_MODEL=your-served-model-id
QWEN_API_KEY=
```

The endpoint must support OpenAI-compatible chat completions and function tool calling. A configured API key is sent as a bearer token. `.env` stays local and is ignored by Git. The local document tools need no model credentials.

## Run either implementation

| Implementation | Command | Control flow |
|---|---|---|
| Python loop | `python -m app.agent` | Loop and conditions in `app/agent.py` |
| LangGraph | `python -m app.workflow.runner` | Nodes and conditional edges in `app/workflow/` |

Both currently ask a fixed example question comparing fictional PDF libraries. Edit the question in the selected entry point's `__main__` block to change it.

Python flow:

```text
Open MCP → Discover tools → Call Qwen → Execute requests → Repeat
                                           └── Final answer → Validate → Return
```

LangGraph flow:

```text
START → Model ── tools requested → Tools ── running → Model
          |                         └── budget exhausted → END
          ├── final answer → Validate → END
          └── failed / model budget exhausted → END
```

Defaults: six model calls, eight tool calls, and a 90-second timeout per model HTTP request. Tool calls execute sequentially. The model HTTP call runs in a worker thread so MCP communication can continue on the event loop. No overall time or monetary budget is enforced yet.

## Files and responsibilities

| File | Purpose |
|---|---|
| `app/agent.py` | Original Python controller; also supplies the Qwen HTTP function reused by the graph |
| `app/search.py` | Three fictional documents and keyword search/read implementations |
| `app/mcp_server.py` | Exposes those functions as MCP tools |
| `app/mcp_tools.py` | Discovers allowed tools, converts definitions for Qwen, invokes tools, and decodes results |
| `app/schemas.py` | Pydantic contracts for reports, findings, and evidence references |
| `app/validation.py` | Checks that cited sources were read and quotes occur in their text |
| `app/workflow/state.py` | Shared research data; messages/trace append, other fields replace |
| `app/workflow/nodes.py` | Model, tool-execution, and report-validation nodes |
| `app/workflow/routing.py` | Selects the next path from updated state |
| `app/workflow/graph.py` | Registers nodes and edges, then compiles the workflow |
| `app/workflow/runner.py` | Opens MCP, prepares initial state, runs the graph, and collects the result |
| `checks/` | Local checks of components and complete execution paths |
| `examples/` | Standalone LangGraph and Python-closure learning exercises |

Use `python -m package.module` from the repository root. The `__init__.py` files identify Python packages. The graph runner currently imports model access from `app.agent`; importing it does not launch the original loop.

## Checks

These commands use local data and simulated model responses, without contacting Qwen:

```bash
python -m checks.check_validation
python -m checks.check_mcp
python -m checks.check_agent
python -m checks.check_model_node
python -m checks.check_routing
python -m checks.check_tool_node
python -m checks.check_report_node
python -m checks.check_graph_agent
```

`check_agent` exercises the original controller; `check_graph_agent` exercises the complete graph. Both use real local MCP subprocesses. The other checks cover discovery, state updates, routing, and validation. Checks importing model access still require the configuration variables in `.env`.

Learning examples:

```bash
python -m examples.check_graph
python -m examples.python_closure
```

## Output and validation boundaries

Results include a status and, where applicable, a report, validation errors, call counts, and tool trace. Reports contain `findings` with `claim`, `source_id`, and `quote` fields nested under evidence references, plus `evidence_gaps`.

- **Schema validation:** checks JSON fields, types, and declared constraints.
- **Evidence-reference validation:** checks that sources were read and quotes match exactly.
- **Claim support:** remains `not_checked`; a real quote can still fail to justify a claim.

`answered` means the implemented checks passed, not that research is complete or every claim is true. Budget exhaustion, invalid reports, and some request failures return explicit outcomes. Connection-level failures can still propagate as exceptions.

## Next milestones

1. Explicit research planning and coverage tracking.
2. External search/retrieval and an independently maintained MCP server.
3. Persistent source/evidence records, semantic claim verification, and conflict handling.
4. Checkpoints, recovery, cancellation, and token/cost accounting.
5. Reproducible baseline comparisons, then an API, interface, and deployment.

The current implementation has no automatic report repair, durable checkpoints, formal benchmark results, or production reliability guarantees. Search is simple keyword matching and currently returns full document text as snippets. MCP decoding is scoped to this project's JSON-object tools.

See the [project blueprint](Project_02_Autonomous_Research_Agent_MCP_Blueprint.md) for the proposed full scope.
