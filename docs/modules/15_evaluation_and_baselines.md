# Module 15 — Reproducible evaluation and baseline comparison

## Why this module exists

A successful demo shows that one run worked. Evaluation asks how often the system handles a defined set of questions, what its citations support, and how much execution it uses. This module supplies a frozen dataset, three comparable systems, independent-from-workflow grading, and saved measurements. It does not establish that the agent is better than retrieval without running and reviewing the benchmark.

## What was implemented

`benchmarks/research_v1.json` contains 15 questions in six categories:

| Category | What it exercises |
|---|---|
| Single hop | Find a directly documented capability or limitation |
| Multiple hops | Combine evidence across documents |
| Missing evidence | Acknowledge that pricing or an accuracy winner is not established |
| Conflicting evidence | Preserve contradictory OCR statements without inventing a resolution |
| Robustness | Handle a controlled first search/read error |
| Untrusted content | Treat an instruction embedded in a document as data |

Every case contains a question, frozen fictional documents, coverage criteria, forbidden assertions, and an optional controlled tool fault. The labels are **authored seed rubrics, not independently reviewed human ground truth**. The small fictional corpus makes evidence inspection and reproducibility practical; it does not represent open-web research difficulty.

The research process sees only the question and tools. The benchmark's expected criteria and forbidden assertions are available only to the offline grader. Tool schemas expose search and read, not labels.

## Three systems

| Variant | Behavior |
|---|---|
| `retrieval` | Search the original question once, read up to three returned sources, ask Qwen for one report |
| `agent_no_followup` | Plan, execute tasks through MCP, assess coverage, synthesize and verify claims; follow-up disabled |
| `agent_followup` | Same workflow with at most one targeted follow-up cycle |

All use the configured Qwen model, the same frozen corpus/search implementation, and the same allowed model/tool caps. Each trial starts a fresh MCP process, resetting injected faults. The baseline is deliberately simple and has no retry loop or planning. It therefore uses fewer calls and does not use all its available budget. The no-follow-up comparison isolates the effect of the feedback cycle more closely than the retrieval comparison does.

The graph runner gained optional trusted host configuration for a fixture MCP server and corpus context. Normal graph defaults are unchanged. Benchmark runs do not use the web, mutate the normal source store, or resume existing research checkpoints.

## Execution

```text
Load and validate dataset
  → Freeze dataset/configuration/code fingerprint
  → For each case × repeat × variant:
      Start fresh fixture MCP server
      Run the chosen system using Qwen
      Save report, trace and research requests
      Check source-read and exact-quote relationships
      Ask Qwen to grade the report against the hidden rubric
      Save grade and separate grading usage
      Update JSON / CSV / Markdown summaries
```

The offline judge receives the candidate report, reference documents, rubric and citation-validity flags. It does not receive variant name, internal workflow status, coverage verdicts or the agent's own verification results. Its assessments do not feed back into research. Qwen is still both the generating and judging model: model-family bias and grading errors remain possible. Review representative successes and failures manually before using accuracy numbers on a resume.

## Measurements and their limits

- **Report production:** schema-valid report present, regardless of whether the workflow accepted it.
- **Rubric coverage:** fraction of seed criteria judged addressed by Qwen.
- **Citation validity:** fraction of references with an exact quotation in a successfully read source. This is deterministic and does not establish semantic support.
- **Claim support:** fraction of claims judged supported by their own citations; invalid citations cannot receive supported credit.
- **Forbidden assertions:** rubric-listed unsupported conclusions endorsed by the report. Quoting or denying one is not endorsement.
- **Confirmed task success:** every rubric criterion met, every finding supported, and no forbidden assertions endorsed. Correct gap-only answers can pass missing-evidence tasks.
- **Efficiency:** research wall time, attempted model calls, tool calls and reported input/output tokens. Offline grading has separate latency, call and token accounting.
- **Estimated cost:** available only when both user-supplied token prices and complete token usage are present. Default cost is unknown (`null`), appropriate for a self-hosted endpoint without a declared price.

No-citation/no-claim ratios are `null`, not perfect scores. Grading failures remain recorded; confirmed successes are divided by all trials, while coverage and claim support explicitly show graded-output denominators. Provider errors without usage increment the missing-usage count. Wall time includes local MCP startup and model waits; it is not GPU inference time. Temperature zero does not ensure identical reruns.

The saved model is Qwen only. Simulated responses in checks test implementation behavior and are never presented as measured Qwen performance.

## Files

| File | Responsibility |
|---|---|
| `benchmarks/research_v1.json` | Versioned frozen cases and seed rubrics |
| `app/evaluation/dataset.py` | Pydantic input validation, deterministic search/read and controlled faults |
| `app/evaluation/mcp_server.py` | Expose a single case's documents through MCP |
| `app/evaluation/systems.py` | Retrieval baseline and graph variants |
| `app/evaluation/grading.py` | Blind rubric/claim grading and deterministic citation metrics |
| `app/evaluation/runner.py` | Trial matrix, saved artifacts, accounting, summaries and benchmark resume |
| `checks/check_evaluation.py` | Faults, citation-versus-support distinction, grading validation, metrics, real MCP trial matrix and resume |

## Run commands

Run from the repository root with the virtual environment active and Qwen configured in `.env`.

```bash
# No hosted model calls: simulated Qwen plus real fixture MCP.
python -m checks.check_evaluation

# Smoke comparison: one question, three variants, one repeat.
python -m app.evaluation.runner --cases scanbridge --max-model-calls 24 --max-tool-calls 16

# Full initial matrix: 15 questions × 3 variants = 45 trials.
python -m app.evaluation.runner --max-model-calls 30 --max-tool-calls 20

# Select difficult cases, or repeat for variability (1–5 repeats supported).
python -m app.evaluation.runner --cases accuracy_winner ocr_conflict read_recovery injection_resistance --repeats 2

# Continue an interrupted benchmark with its original code and model configuration.
python -m app.evaluation.runner --resume runs/evaluations/<benchmark-run-id>
```

The full matrix can use many Qwen calls: agent budgets are per trial, and one offline grader call is additional. Start with a smoke test. Optional `--input-price-per-million` and `--output-price-per-million` must both be finite, nonnegative USD rates supplied by you; the application does not invent endpoint prices.

Benchmark resume skips cells with completed row files, including completed failures. It reruns an interrupted cell from the beginning; it does not resume that trial's graph state. Already completed failure rows are retained as evidence, not silently retried until success. Keep the original code and model configuration for resume; start a new benchmark after code changes.

## Saved records

Under `runs/evaluations/<id>/`:

```text
manifest.json          # Cases, variants, limits, model, dataset hash, code fingerprint, versions
 dataset.json          # Frozen dataset snapshot
 run.log               # Overall progress
 rows/*.json           # Completed trial records (resume boundary)
 summary.json          # Aggregate statistics
 summary.md            # Readable comparison with limitations
 results.csv           # Per-trial metrics for analysis
 completion.json       # Attempted/expected trial counts
 trials/<case>/<variant>/<trial-id>/
   run.json            # Trial identity and benchmark link
   case.json           # Fixture and hidden grading policy
   result.json         # Research output and trace
   grade.json          # Offline assessment and deterministic metrics
   model_calls.jsonl   # Research/grading requests, responses and errors
   run.log             # Trial progress
```

Run artifacts are ignored by Git. Keep desired results separately if sharing a portfolio case study. Requests contain the question, documents and grader rubric, so inspect files before publication.

## Interview points

**Why compare against a simple baseline?** To measure whether planning and extra calls improve results enough to justify latency and execution cost.

**Why frozen documents rather than live web alone?** Changing search results, pages and failures otherwise confound comparisons. A frozen test measures controlled behavior; a separate live-web campaign measures external generalization.

**Why separate citation validity from support?** An exact quotation can be irrelevant to the claim. Provenance validation and semantic entailment answer different questions.

**Why not trust the agent's own confidence?** Evaluation must assess saved outputs against an external rubric. The offline judge is isolated from internal verdicts, although using the same model still requires human calibration.

**Does a higher score prove improvement?** Not on one smoke question. Inspect per-case failures, use repeated matched trials, review labels/judgments and report sample size. These seed cases are engineering tests, not a public standardized benchmark.

## What remains

Run and review the full matrix, improve the seed labels with independent review, inspect failure cases, and write a measured portfolio comparison. Large-scale open-web benchmarks, independent judges, statistical significance analysis and production telemetry are outside this module's implemented scope.

## Verification in this implementation

All 25 deterministic check modules passed. Live Qwen smoke run `20261117T114856_902731Z_56607cb7` completed the `scanbridge` question under all three variants. All reports had valid citations and passed the offline seed rubric. Research model/tool counts were 1/4 for retrieval, 13/9 without follow-up, and 20/12 with follow-up; each had one additional offline grading call. One follow-up cycle actually executed. On this simple question, extra orchestration increased execution without changing the rubric outcome. The full 45-trial campaign has **not** been run, and these grades are not independently reviewed accuracy results.

Its saved `validation.md`, `summary.md`, `results.csv`, and trial journals explain the observations. Code changes invalidate resume compatibility for historical checkpoint sessions; keep the code version used by a run when planning to resume it.
