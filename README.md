# Traceable Research Agent

A Python research-agent project focused on inspectable tool execution, structured evidence, and auditable reports.

**Status:** early learning and implementation milestone. The current scripts use fictional local documents, a hosted Qwen endpoint, and a local MCP server over stdio. Semantic claim verification, persistent state, and benchmarking remain planned.

## Project goal

Build a bounded autonomous research agent that decomposes questions, discovers and invokes tools through MCP, preserves evidence provenance, identifies missing or conflicting evidence, and produces cited reports. Evaluate its quality and resource use against simpler retrieval and tool-calling baselines.

The project grows incrementally: understand a concept, implement it, inspect its behavior, and extend the system.

## Current implementation

- MCP discovery of two tools: `search_sources` and `read_source`.
- Translation of MCP tool definitions into Qwen's chat-completion tool format.
- Explicit client-side tool allowlist and JSON-object argument checks; tool schema validation is handled by the server SDK.
- A conversation loop that returns tool observations to the model.
- Configurable model-call and tool-call limits.
- In-memory tool traces, including the model-call number.
- Pydantic schemas for findings, evidence references, and evidence gaps.
- Checks that cited sources were successfully read and quoted passages occur in their text.
- Explicit outcomes for answers, invalid reports, exhausted budgets, and some request/response failures.

The sample task compares two **fictional** PDF-processing libraries. These documents are controlled inputs for learning and debugging; they are not real product research.

## Execution flow

```text
Question + tool definitions
          |
          v
    Hosted Qwen model
          |
          +-- Tool requests --> MCP adapter --> MCP stdio server
          |                                      |
          |                         Append results to conversation
          |                                      |
          +<-------------------------------------+
          |
          +-- Final JSON --> Validate report structure
                                 |
                         Check sources and quotes
                                 |
                           Return result
```

The model proposes actions. Python validates and executes them, records observations, and enforces call limits. Tools currently execute sequentially.

## Repository layout

```text
.
├── agent.py                  # Model requests, MCP lifecycle, controller, trace, validation
├── mcp_tools.py              # Discovery adapter, allowlist, invocation, result decoding
├── mcp_server.py             # Exposes the search/read tools over stdio
├── check_mcp.py              # Real MCP discovery and invocation smoke check
├── check_validation.py       # Schema and source-reference validation exercises
├── check_agent.py            # Real MCP loop with simulated model responses
├── search.py                 # Fictional documents and local search/read functions
├── schemas.py                # Pydantic report and evidence contracts
├── requirements.txt          # Python dependencies
├── .env.example              # Configuration template
├── .gitignore
├── README.md
└── Project_02_Autonomous_Research_Agent_MCP_Blueprint.md
```

## Setup

Use Python 3.11 or newer. From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

If `.env` already exists, edit it instead of copying over it.

Configure your own endpoint and its exact served model identifier:

```dotenv
QWEN_BASE_URL=http://localhost:8100/v1
QWEN_MODEL=replace-with-the-served-model-id
QWEN_API_KEY=
```

The endpoint must support OpenAI-compatible `POST /v1/chat/completions` requests, function tool definitions, assistant tool calls, and tool-result messages. A `/v1` base URL alone does not guarantee these capabilities.

If configured, `QWEN_API_KEY` is sent as a bearer token. The local document server does not require model credentials.

Keep `.env` local. It is excluded by `.gitignore`; share `.env.example` as the configuration template.

## Run

```bash
python agent.py
```

The application launches the local MCP server automatically and keeps its connection open for the run. No separate terminal or HTTP port is needed. Blocking model HTTP requests run in a worker thread so the event loop can service MCP communication; tool calls remain sequential.

## Local checks

```bash
python check_validation.py
python check_mcp.py
python check_agent.py
```

These checks do not call the model endpoint. `check_agent.py` substitutes deterministic model responses while exercising the real MCP subprocess, conversation history, report validation, and call limits. Currently, importing `agent.py` still requires the model configuration variables in `.env`.

The question is currently defined in the `__main__` block of `agent.py`. Edit that question to try another task over the same fictional collection.

The result is printed as JSON. An accepted report includes findings with source IDs and exact quotes, evidence gaps, validation check results, model/tool call counts, and a tool trace. Error and budget-exhaustion responses include the reason and accumulated trace.

Defaults are six model calls and eight tool calls per run, with a 90-second timeout per HTTP request. These are not an overall wall-clock or monetary budget.

## Understanding validation

| Check | What it establishes |
|---|---|
| Pydantic schema | The JSON has the declared fields, types, and constraints |
| Source reference | The cited source was successfully read during this run |
| Exact quote | The quoted string occurs in the retrieved source text |
| Claim support | Not implemented: whether the quote actually justifies the claim |

A genuine quote can still be attached to an unsupported claim. `status: answered` means the report passed the implemented checks; it does not establish factual correctness, research completeness, or semantic support. Reports explicitly mark claim support as `not_checked`.

## Current limitations

- No external search, independent third-party MCP server integration, explicit planner, or persistent storage.
- MCP result decoding currently expects JSON objects for this project's tools, not arbitrary multimodal results.
- Connection-level failures can propagate as exceptions; comprehensive recovery and malformed-response handling remain future work.
- Search uses simple keyword matching over three local documents and returns their full text as snippets.
- Structured JSON is requested through prompting, then validated locally; invalid reports are not automatically repaired.
- Exact quote matching is sensitive to whitespace and punctuation differences.
- No semantic verification, source credibility scoring, or conflict-resolution mechanism.
- No retry/recovery system, token/cost accounting, automated benchmark suite, or measured performance results.
- The controller is a learning implementation, not a hardened production runtime.

## Roadmap

1. Validate the basic tool loop and structured-report behavior.
2. Extend the local MCP integration with external retrieval and an independently maintained server.
3. Introduce explicit research tasks, evidence records, and adaptive planning.
4. Assess claim support, missing evidence, and contradictions.
5. Add persistence, checkpoints, bounded retries, and operational tracing.
6. Compare against search-and-summarize and simpler tool-calling baselines.
7. Deliver an API, interface, reproducible deployment, and measured case study.

The [project blueprint](Project_02_Autonomous_Research_Agent_MCP_Blueprint.md) describes the broader proposed scope. Its architecture and roadmap should not be interpreted as completed capabilities.
