# 11 — External retrieval through MCP

[Module index](README.md) · [Current project status](../../README.md)

## Purpose

The agent can now investigate external documents instead of only the three fictional examples. The planning, task, coverage, synthesis, and quote-validation architecture stays the same. The MCP server selects a source backend at startup.

Qwen is the model used for planning, research, coverage, JSON repair and synthesis. The CLI uses the existing QWEN_BASE_URL, QWEN_MODEL and QWEN_API_KEY configuration without provider fallback. Wikipedia and Tavily are source-retrieval services, not alternative models. Simulated responses are only used in automated checks.

## Architecture and flow

```text
Question + retrieval configuration
  → runner supplies scope to planner and research model
  → model requests search_sources(query)
  → MCP server uses Wikipedia or Tavily
  → search results become registered source IDs
  → model requests read_source(source_id)
  → validate destination → download → extract text → cache
  → task findings cite source ID + exact quote
  → existing validation checks the read text
  → final output includes a sources metadata inventory
```

The MCP protocol remains the same. We changed the implementation behind the tools, not the agent's tool names. This is the practical benefit of the boundary built in module 03.

## Files

| File | Responsibility |
|---|---|
| `app/retrieval/settings.py` | Validate environment configuration, describe research scope, pass only retrieval settings to the subprocess |
| `app/retrieval/web.py` | Provider requests, source registration, URL checks, page downloads, HTML extraction, caching and provenance |
| `app/mcp_server.py` | Choose local or web backend and expose the two tools |
| `app/planning/planner.py` | Build a plan within the configured retrieval scope |
| `app/workflow/state.py` | Carry `research_context` into planning |
| `app/workflow/nodes.py` | Pass that context to the planner |
| `app/workflow/runner.py` | Configure MCP, CLI question/budgets and output source inventory |
| `checks/check_web_retrieval.py` | Deterministic mocked HTTP tests; no model or network |
| `checks/check_web_graph.py` | Complete graph with real in-process MCP, mocked HTTP and a simulated model |
| `checks/check_web_live.py` | Explicit live search/read through the MCP subprocess; no model |

The original Python controller remains a local example. The new web CLI is the LangGraph runner.

## Configuration and use

Keep the existing QWEN variables in `.env`. Add the retrieval variables from `.env.example`. Existing files are not rewritten automatically.

```dotenv
RESEARCH_BACKEND=local
WEB_SEARCH_PROVIDER=wikipedia
TAVILY_API_KEY=
WEB_ALLOWED_DOMAINS=en.wikipedia.org,docs.python.org,modelcontextprotocol.io,docs.langchain.com
WEB_MAX_RESULTS=3
WEB_TIMEOUT_SECONDS=15
WEB_MAX_BYTES=2000000
WEB_MAX_TEXT_CHARS=100000
```

From the repository root, with the virtual environment active:

```bash
# No network and no model:
python -m checks.check_web_retrieval
python -m checks.check_web_graph

# Real external search/read through MCP, without spending model calls:
python -m checks.check_web_live --query "Python programming language"

# Existing fictional research:
python -m app.workflow.runner --backend local

# Actual external research (uses the configured LLM endpoint):
python -m app.workflow.runner --backend web \
  --question "What are Python generators and how do they differ from coroutines?" \
  --max-model-calls 20 --max-tool-calls 15
```

Wikipedia mode is key-free **Wikipedia search only**. Having Python or MCP domains in the allowlist does not make Wikipedia search discover their documentation pages. A Wikipedia article is not automatically a primary source. Use this mode to learn and test retrieval, and record gaps when its scope cannot answer a question.

For broader search, set `WEB_SEARCH_PROVIDER=tavily`, provide your own `TAVILY_API_KEY`, and choose relevant `WEB_ALLOWED_DOMAINS`. Tavily can incur provider charges. No Tavily request was needed for deterministic verification. There is no silent provider fallback. `--backend` overrides `RESEARCH_BACKEND`; web CLI runs require an explicit question.

The host loads `.env` and explicitly passes retrieval settings to the MCP child. Directly launching `app.mcp_server` requires exported environment variables; the server itself does not load `.env`.

## Important implementation concepts

**Discovery versus evidence:** search snippets help find sources. A successful `read_source` supplies the text accepted by the quote validator. Search alone does not permit citing a source.

**Source registry:** a canonical URL is hashed into a stable `web_...` ID. The server only reads IDs discovered during that run; a model cannot submit an arbitrary URL to `read_source`. Duplicate URLs share an ID. Different URLs containing the same article are not deduplicated by content.

**Caching:** repeated reads return the same successful text within one MCP process. This keeps quote checks consistent if a live page changes during research. A new run starts a new registry and cache.

**Provenance:** successful reads include original and resolved URLs, discovery/retrieval times, media type, truncation flag, a SHA-256 hash of the retained text, and a hash of the downloaded response bytes after HTTP decompression. The final `sources` mapping resolves citation IDs to metadata. Full extracted text remains in the tool trace. Hashes identify content; they do not prove it is true or independently archive the page.

**Controlled retrieval:** approved domains and their subdomains, HTTPS, public-address DNS checks, bounded redirects, response-size limits, text limits, and timeouts constrain downloads. Provider credentials are sent to the fixed search API, never attached to page requests. Proxy and `.netrc` inheritance are disabled for page retrieval. Failures return short error codes rather than raw request details.

**Budgets:** agent tool calls still count against the existing tool budget. A tool invocation may perform multiple HTTP operations; the tool budget is not an HTTP-request or monetary budget. HTTP timeouts are connect/read inactivity limits, not an absolute whole-run deadline.

## Checks and limitations

The deterministic suite exercises discovery, stable IDs, cache behavior, metadata/hashes, allowlists, private DNS, redirect blocking, response/text limits, unsupported content, timeouts, provider errors, Tavily request shape, extraction and planner scope. All 17 pre-existing check modules passed after integration. The 13 new deterministic retrieval tests passed, and the full web graph passed using real in-process MCP, mocked HTTP and six simulated model calls. The live check also passed: the MCP subprocess searched Wikipedia and downloaded the Python article, returning text and provenance without calling Qwen. The article exceeded the configured text limit and was explicitly marked truncated. Tavily was verified with mocked HTTP only; no live Tavily key was configured.

Only HTML and plain text are supported. The extractor is deliberately simple: no PDF parsing, browser rendering, login, citation-span offsets or durable snapshots. Page text is untrusted; prompts instruct the model to treat it as data, but this is not a complete prompt-injection defense. DNS checks are not connection-pinned, so they do not eliminate DNS rebinding; production deployment needs network-level egress restrictions. A domain allowlist does not establish source quality.

Later modules implement semantic verification (12), bounded follow-up (13) and checkpoint/source-state recovery (14). A dedicated evidence database and independently maintained third-party MCP server integration remain outside scope; this project exposes its own MCP server.

## Interview questions

- **Why retain the same MCP tool names?** The controller consumes a stable discovery/read contract while the source implementation changes behind it.
- **Why not cite search snippets?** They can be incomplete or stale and are not the text used by the evidence validator.
- **Does a matching quotation prove a claim?** No. It proves textual occurrence in a retrieved source. Entailment and source reliability need further checks.
- **Why cache and hash source text?** To identify the evidence version and keep repeated reads consistent within a run; persistence is needed for later reproducibility.

Provider references: [MediaWiki search API](https://www.mediawiki.org/wiki/API:Search) and [Tavily search API](https://docs.tavily.com/documentation/api-reference/endpoint/search).


## Saved Qwen runs

Every `python -m app.workflow.runner ...` invocation now saves a unique folder automatically:

```text
runs/<UTC-timestamp>_<unique-id>/
├── run.json             # Question, Qwen endpoint/model, budgets, start/end and status
├── run.log              # Workflow progress and handled/unexpected failures
├── model_calls.jsonl    # Incremental model requests, responses and errors
├── result.json          # Final success or failure, findings and available task records
└── trace.json           # Available tool execution trace, including retrieved text
```

The default workflow budgets are 60 model calls and 60 tool calls. Override them with `--max-model-calls` and `--max-tool-calls`. Higher limits permit longer research but do not guarantee completion.

The terminal still shows progress and final JSON. `artifacts_dir` in the result points to the saved folder. Choose another location with `--output-dir /path/to/records`. Existing folders are not overwritten.

```bash
python -m app.workflow.runner --backend web \
  --question "What are Python generators?" --output-dir runs
```

The shared `run_saved_research()` entry point in `app/workflow/runner.py` wraps the graph, and `app/workflow/artifacts.py` handles recording. Future modules can reuse this entry point. `run_graph_agent()` remains the lower-level execution function for component tests; calling it directly does not save artifacts. The original `app.agent` learning CLI also retains its previous behavior.

Model requests are written before sending, followed by response/error records with matching call IDs. This includes planning, repair, coverage and synthesis calls. A refused Qwen connection is therefore retained as a failed run instead of disappearing with terminal history. There is no automatic fallback to another model or automatic replay of failed research.

Known configured Qwen/Tavily key values are redacted in saved files. Questions, retrieved text and model output are intentionally retained; `runs/` is ignored by Git. This is not general personal-data redaction, and custom output directories need their own ignore rule if inside the repository.

These JSON/log records alone are not resumable checkpoints. The normal CLI now also persists LangGraph checkpoints and source state as described in module 14. Handled failures retain available graph results. Unexpected exceptions or cancellation save an outcome and already-written model records, but may lack the partial graph/tool trace. A force-killed process or disk failure cannot guarantee a final result file. Log capture is designed for one saved workflow at a time in a process.

Verification: `python -m checks.check_run_artifacts` checks success, handled failure, unexpected failure, cancellation, request/error recording, and configured-secret redaction without contacting Qwen. A live Qwen/Qwen3.8-27B run on 2026-11-17 verified planning, MCP web search/read, JSON repair, task validation and coverage. It stopped at the tool limit after 14 model calls and 15 tool calls, with one of three tasks completed and four sources read; final synthesis was not reached. Run ID: `20261117T083355_497643Z_b534789c`. Saved artifacts and a `validation.md` note are under that run folder. This is partial live validation, not a successful complete research run.

## Reliability changes after live Qwen failures

The earlier runs exposed two distinct failures: repeated research exhausted the tool limit, and Qwen eventually returned `content: null` with only a reasoning field. Raising the global budget did not resolve either behavior.

The current implementation adds:

- **Qwen request controls:** non-thinking chat-template mode, a 4,096-token response limit, and JSON object output mode for steps without tools. Response records retain `finish_reason` and token usage when supplied by the endpoint. Reasoning is never treated as an answer or evidence. The server must support these Qwen/vLLM request options; incompatible settings return an error rather than silently changing providers. See [Qwen deployment documentation](https://qwen.readthedocs.io/en/stable/deployment/vllm.html).
- **Scoped plans:** in Wikipedia mode, explicit official/primary-documentation requirements introduced by the planner are changed to available Wikipedia evidence before task initialization. Original changed fields are retained in `plan_scope_adjustments`. This normalization covers common source qualifiers; it is not a general semantic validator of arbitrary plans. The user's question remains unchanged, and source restrictions must remain visible in the report.
- **Per-task limits:** three research turns followed by a tool-free extraction/conclusion request. Each task permits at most two non-cached search requests and six tool requests before further tool operations are refused. Duplicate successful requests reuse the existing result. Tool requests, including cached/refused operations, still consume the global call allowance. This is bounded investigation, not an evidence-quality stopping algorithm.
- **Compact evidence views:** each request is reconstructed for the current task from the system contract, task guidance, up to six successfully read sources, and the two most recent searches. Each source contributes at most 5,000 characters selected by query relevance from exact source substrings. Full extracted text stays in the trace. There is no generated evidence summary and no claim that these passages cover the whole source.
- **Larger retained page text:** the default is now 100,000 extracted characters per source, still subject to the 2 MB response bound. This avoids discarding relevant sections of long Wikipedia articles before passage selection. Explicit `.env` values override this default; update `WEB_MAX_TEXT_CHARS` if your existing file sets a smaller value.
- **Partial findings:** the forced conclusion uses a dedicated evidence-extraction instruction. Individually supported facts are retained even when other criteria require evidence that was not found. Unsupported details remain gaps; coverage is assessed separately.
- **One empty-response retry:** an empty web task response may use the existing single per-task repair allowance to request a new JSON result from retained evidence. Reasoning text is excluded. A second invalid response still stops the run. Nonempty malformed JSON retains the existing format-repair path; evidence/task-ID errors are not bypassed.
- **Synthesis capacity:** when only two model calls remain at task selection, uninvestigated tasks become explicitly unresolved with gaps and the graph routes to synthesis. During research, low remaining budget disables further tools. This is a small fixed reserve, not dynamic cost scheduling; transport or later validation failures can still prevent a report.

Implementation lives in `app/workflow/research_policy.py`, the existing workflow nodes/state/runner, `app/agent.py`, and retrieval settings. Local learning checks retain their original flow; the bounded investigation policy is enabled for the web backend. Qwen request controls apply to both entry points.

Run `python -m checks.check_research_policy` for the regression cases: scope normalization, exact bounded passages, Qwen request configuration, forced conclusion, refusal of excess searches, empty-response recovery without reasoning, and synthesis reservation. A completed report can still contain unresolved tasks; `answered` means output validation passed, not that all evidence requirements were satisfied. Semantic verification was not part of this module-11 milestone; it is now implemented in module 12.


### Latest live acceptance run

Run `20261117T092012_810828Z_88b1b7de` completed using Qwen with **12 model calls, 8 tool requests, 6 findings and 3 explicit evidence gaps**. The first task was assessed answered and the second unresolved; final synthesis and schema/source/quote validation passed. Recorded prompts stayed below 24,509 characters, compared with approximately 251,000 in the failing run. Stored source hashes and report references were checked again from saved files.

See `runs/20261117T092012_810828Z_88b1b7de/validation.md`, `result.json` and `run.log` locally. Run artifacts are ignored by Git. Earlier gap-only runs are preserved rather than overwritten. This validates one complete live workflow with honest limitations; semantic verification and broader benchmarks were still pending at that milestone and were subsequently implemented in modules 12 and 15.
