# Autonomous Research Agent

An evidence-grounded research agent built with **Python, LangGraph, MCP, Qwen, Pydantic and SQLite**. It plans investigations, retrieves documents, produces cited findings, checks claim support, and can perform one targeted follow-up within execution limits.

The agreed learning and portfolio scope is implemented. All 25 deterministic check modules passed, and the initial 45-trial frozen-document evaluation is complete. This is a CLI project; an API, UI and hosted deployment are optional extensions.

## Architecture

```text
Question → Plan → Select task → Research model ⇄ MCP search/read
                     ↑                |
                     └── Assess coverage ← Collect/validate task result

No pending tasks → Synthesize → Validate citations → Verify claim support
                                                       |
                         Select follow-up ← Decision → Finish
                         (at most one cycle)
```

Qwen proposes actions and assesses evidence. Python enforces permitted tools, validation and budgets. MCP discovers and invokes search/read tools across a process boundary. LangGraph manages state and routing; SQLite checkpoints let the normal graph CLI resume pending work after interruption.

The original Python-loop implementation remains available for learning. It has no planning, coverage, semantic verification or follow-up stages.

## Setup

Use Python 3.11+ on Linux/macOS and run commands from the repository root. The persistence implementation uses Unix file locking; on Windows, use WSL.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# Only if you do not already have .env:
cp .env.example .env
```

Configure your hosted Qwen endpoint and its exact served model identifier:

```dotenv
QWEN_BASE_URL=http://localhost:8100/v1
QWEN_MODEL=your-served-model-id
QWEN_API_KEY=
```

The endpoint must support OpenAI-compatible chat completions, function tool calling and JSON output. The benchmark used `Qwen/Qwen3.8-27B`. The repository does not host the model. `.env` is ignored by Git; `.env.example` contains configuration names and defaults.

## Run

```bash
# Complete graph, default fictional PDF-library question:
python -m app.workflow.runner

# Original Python tool loop:
python -m app.agent

# Web research, using the configured provider:
python -m app.workflow.runner --backend web --question "What are Python generators?"

# Inspect or resume a graph CLI run:
python -m app.workflow.runner --inspect runs/<run-id>
python -m app.workflow.runner --resume runs/<run-id>
```

Local mode searches three fictional documents. Web mode defaults to Wikipedia; optional Tavily needs its own key and approved domains. Retrieval applies domain/network checks, bounded downloads and text extraction, caching, stable source IDs and content hashes. See [retrieval configuration](docs/modules/11_external_retrieval.md).

Graph defaults are 60 model calls and 60 tool requests per run; the original loop defaults to six and eight. Planning, coverage, repair, synthesis and verification consume model budget. Web and benchmark research also have per-task allowances. Requests have a 600-second HTTP timeout; no overall wall-time or monetary cap is enforced. Tools execute sequentially, and blocking model calls run in a worker thread.

Use `--max-model-calls`, `--max-tool-calls` and `--max-followup-cycles 0` to control a new graph run. Resume preserves the saved configuration and budgets; it does not grant more calls. Code/model changes invalidate resume compatibility. See [checkpoint behavior and limits](docs/modules/14_checkpoint_persistence.md).

## Evidence and failure handling

Reports contain `findings`, each with a claim and evidence references (`source_id`, exact `quote`), plus `evidence_gaps`.

- **Structure:** Pydantic checks fields, types and constraints.
- **Citation validity:** Python checks that a source was successfully read and the quotation occurs in its text.
- **Claim support:** Qwen assesses whether the cited evidence supports every material part of a finding. Partial or unsupported findings retain the report with `invalid_report` for review.
- **Coverage:** Qwen assesses task criteria. Unresolved tasks and evidence gaps can remain in an accepted report.
- **Recovery:** one bounded task-JSON repair; local durable checkpoints, restored source snapshots and attempt-bounded request replay for pending work.

`answered` means the configured checks passed, not that every task was resolved or every statement is true. The original Python loop does not assess semantic support. Exact quotes do not prove entailment or source credibility; Qwen judgments are fallible. The semantic gate assesses findings, not every free-text gap. Source IDs and quotes are tracked, but a dedicated evidence database and systematic conflict detection are not implemented.

## Saved records

Graph CLI runs save configuration, timestamped logs, model request/response/error journals, results, tool traces, follow-up history, verification assessments, SQLite checkpoints and supporting recovery records under `runs/<id>/`. Progress goes to stderr; the final result is JSON on stdout. Importing the runner does not start a run.

Configured API key values are redacted. Run records can contain questions and retrieved text; they remain local and are ignored by Git. Unexpected failures may leave only incremental records, and completed terminal failures are not automatically retried. See [saved artifacts](docs/modules/11_external_retrieval.md#saved-qwen-runs).

## Evaluation results

On 2026-11-17, Qwen completed **15 questions × three variants = 45 trials**, one repeat each, against frozen fictional documents. Both agent variants had 60-model/60-tool ceilings. The retrieval baseline searches once, reads up to three sources and makes one synthesis call.

| Variant | Offline rubric successes | Workflow accepted | Validated offline grades | Mean research time | Mean model / tool requests |
|---|---:|---:|---:|---:|---:|
| Retrieval only | 12/15 | 15/15 | 15/15 | 9.0 s | 1.0 / 3.7 |
| Agent without follow-up | 13/15 | 12/15 | 14/15 | 95.0 s | 14.7 / 9.6 |
| Agent with follow-up | 15/15 | 13/15 | 15/15 | 133.9 s | 20.9 / 12.8 |

All **155 emitted references** passed source-read/exact-quote checks. Each trial used one additional offline grading call, excluded from research time and model counts above. Tool counts include cached and policy-rejected requests. Input/output token usage is saved; dollar cost is unknown because no endpoint prices were supplied.

Follow-up received higher offline scores with substantially greater execution usage. **15/15 offline successes is not 100% end-to-end reliability:** two follow-up reports were rejected internally for claims broader than their citations. One no-follow-up grade failed evidence-index validation and remains unscored, with the trial retained in the success-rate denominator. Baseline workflow acceptance has no semantic gate.

These are authored seed rubrics and same-model judgments. The grader is blind to variant names and internal verdicts, but has full reference documents. Focused assistant review found it overlooking scope qualifiers. Independent human review, repeated trials and open-web generalization remain unestablished. Read the [results and case review](docs/evaluation/research_v1_results.md), [45-trial measurements](docs/evaluation/research_v1_trials.csv), and [provenance](docs/evaluation/research_v1_provenance.json).

```bash
# One-question smoke comparison:
python -m app.evaluation.runner --cases scanbridge --max-model-calls 24 --max-tool-calls 16

# Full matrix; can require hundreds of Qwen calls:
python -m app.evaluation.runner --max-model-calls 60 --max-tool-calls 60

# Continue an interrupted benchmark using the original code/model configuration:
python -m app.evaluation.runner --resume runs/evaluations/<benchmark-id>
```

Benchmark resume skips completed cells and restarts an interrupted cell; it does not resume that trial's graph checkpoint. Completed failures remain recorded. Offline grades never feed back into the trial. Details and optional token-price arguments are in [module 15](docs/modules/15_evaluation_and_baselines.md). Original benchmark records remain under `runs/evaluations/20261117T123834_829810Z_e1629ab5/`; the public exports preserve their measurements without raw prompts or endpoint details.

## Checks and learning

Representative checks use simulated models and local/mocked sources, without hosted Qwen calls:

```bash
python -m checks.check_graph_agent
python -m checks.check_claim_verification
python -m checks.check_followup
python -m checks.check_persistence
python -m checks.check_evaluation
```

The latest full regression run passed all **25 deterministic check modules**. A separate `python -m checks.check_web_live` performs real Wikipedia retrieval through MCP without Qwen. Tavily has mocked-test coverage only. Checks importing model access require the configuration names in `.env`. Test success covers the exercised scenarios, not general production reliability.

Use `python -m package.module` from the repository root so sibling packages resolve correctly. [Module notes 01–15](docs/modules/README.md) explain the code, Python closures/async, state, routing, validation, checks and interview concepts. Earlier notes identify learning milestones; the root README describes the current implementation.

## Repository map

| Location | Responsibility |
|---|---|
| `app/agent.py` | Original controller and shared Qwen HTTP function |
| `app/search.py`, `app/mcp_server.py`, `app/mcp_tools.py` | Local fixtures, MCP server selection, discovery, schema conversion and invocation |
| `app/retrieval/` | Web providers, bounded page reads, source metadata and access checks |
| `app/schemas.py`, `app/validation.py` | Report contracts and source/quote validation |
| `app/planning/` | Plans, tasks, coverage, task results and follow-up selection |
| `app/workflow/` | State, nodes, routing, graph, CLI, research limits, artifacts and persistence |
| `app/verification/` | Semantic claim checks and saved-report verification |
| `app/evaluation/`, `benchmarks/` | Frozen fixtures, variants, grading and accounting |
| `checks/`, `examples/` | Controlled checks and learning exercises |
| `docs/modules/`, `docs/evaluation/` | Learning notes, measured results and focused failure review |

`examples/result1.json` is a historical local-data output, not the current benchmark or a schema guarantee. To verify a saved report with Qwen without repeating research, use `python -m app.verification.runner --input-run runs/<run-id>`.

## Scope and extensions

The CLI research workflow, evidence checks, one follow-up cycle, local checkpoint recovery, evaluation framework and initial results are complete for this portfolio scope. Optional extensions include independent judge calibration, repeated/broader benchmarks, richer evidence records, systematic conflicts, third-party MCP servers, and an API/UI/deployment. FastAPI, PostgreSQL, Langfuse and Docker are not part of this implementation.
