# Completed module notes

These notes explain the 15 completed modules in learning order. The agreed CLI portfolio scope and initial evaluation are complete. Earlier live runs and check counts document milestones; use the [project README](../../README.md) for the current implementation snapshot. The broader blueprint includes optional work that has not shipped.

## Reading order

| Module | Topic | Main result |
|---|---|---|
| [01](01_python_tool_loop.md) | Python environment and tool loop | Model requests become bounded application actions |
| [02](02_structured_reports_and_provenance.md) | Structured reports and provenance | Validate output shape, read sources, and exact quotes |
| [03](03_mcp_integration.md) | MCP integration | Discover and invoke tools across a process boundary |
| [04](04_langgraph_orchestration.md) | LangGraph and Python foundations | Explicit shared state, nodes, routing, closures, and async execution |
| [05](05_research_planning.md) | Research planning | Generate a bounded, environment-aware plan |
| [06](06_task_execution_and_results.md) | Task execution | Select, investigate, validate, and store individual task results |
| [07](07_coverage_assessment.md) | Coverage assessment | Assess every task criterion and conclude the task |
| [08](08_report_synthesis.md) | Final synthesis | Combine task results and validate the final report |
| [09](09_bounded_json_repair.md) | Bounded JSON repair | Recover from malformed task JSON once per task |
| [10](10_monitoring_and_checks.md) | Monitoring and checks | Inspect progress and exercise controlled failure cases |
| [11](11_external_retrieval.md) | External retrieval | Configurable Wikipedia/Tavily discovery, bounded page reads and source metadata |
| [12](12_semantic_claim_verification.md) | Semantic claim verification | Qwen verdicts for claim support, with a final review gate |
| [13](13_bounded_followup.md) | Bounded follow-up | One targeted research cycle driven by weak support or unresolved coverage |
| [14](14_checkpoint_persistence.md) | Persistent checkpoints | SQLite state, MCP source restoration and process restart recovery |
| [15](15_evaluation_and_baselines.md) | Evaluation and baselines | Frozen cases, three variants, blind rubric grading and saved comparison metrics |

Modules are learning boundaries, not separate deployed services. Several share functions in `app/workflow/nodes.py`.

## Current architecture

```text
START → Planner → Select task → Model ⇄ MCP tools
                     ↑           |
                     └── Assess ← Collect task result
                                    └── Malformed JSON → Repair once → Collect

No pending tasks → Synthesize → Validate report → Verify claim support
                                                       |
                         Select follow-up ← Decision → END
                         (at most one cycle)
Handled failures or exhausted budgets → END with available records
```

The host application owns research decisions and limits. The model proposes actions. MCP connects tools. LangGraph coordinates execution. Validation accepts only the properties we actually check.

## Run commands

From the repository root with the virtual environment active:

```bash
python -m app.agent                  # Original Python-loop implementation
python -m app.workflow.runner        # Current task-driven LangGraph implementation
python -m checks.check_graph_agent   # Simulated model + real local MCP
```

The original loop does not include the newer planning/task/coverage/repair workflow. The graph reuses its `call_model()` HTTP function.

## Completion and boundaries

A shared live result demonstrated all three tasks assessed, two JSON repairs, and a final accepted report using 18 model calls and 15 tool calls. That is one controlled example, not a benchmark or a general reliability guarantee. Later edits may change behavior and settings.

After module 11, all 17 existing check modules passed again. Thirteen retrieval tests, a full simulated web graph, and live Wikipedia search/read through MCP also passed. No Qwen calls were made for this verification.

Local mode uses three fictional documents; web mode supports Wikipedia or Tavily search and bounded HTML/plain-text retrieval. The graph now assesses claim support with Qwen after deterministic validation; the original loop remains `not_checked`. Coverage is a fallible model assessment; source and quote checks do not establish truth. Normal graph CLI runs now use SQLite checkpoints and a persisted MCP source store; evidence-ID lists remain placeholders.

## Optional extensions and known limits

- Integration with an independently maintained MCP server (our own server now supports external retrieval).
- Persistent source/evidence records, deduplication, and claim/task links.
- Systematic conflicts, verifier calibration and uncertainty evaluation.
- More sophisticated follow-up selection and information-gain stopping (one bounded feedback cycle is implemented).
- Broader transport recovery, checkpoint migrations and dynamic budget allocation (local checkpoint/resume is implemented).
- Independent benchmark label/judge review, repeated evaluations, broader time/token/cost enforcement and security hardening (the first 45-trial campaign is complete).
- API/UI and deployment. The initial measured comparison and focused failure review are available in the [evaluation report](../evaluation/research_v1_results.md).

Model portability has been discussed, but a dedicated provider adapter and alternate backend validation have not been implemented.

Latest module-11 acceptance: live Qwen run `20261117T092012_810828Z_88b1b7de` reached a final validated report with six findings and three gaps using 12 model calls and eight tool requests. One task remained unresolved. All 21 deterministic check modules passed after the reliability fixes; the final extraction-prompt change also passed the policy and complete-web-graph checks. See module 11 for controls and remaining limitations.

Module 12 is implemented: the default graph now gates final reports on Qwen claim-support assessments. Saved-report replay and a fresh full workflow each assessed five claims supported and one partially supported, retaining the report for review. All 22 deterministic check modules passed; see module 12 for details.

Module 13 live acceptance: `20261117T104559_905417Z_4e2b6590` used one follow-up cycle and finished with eight claims assessed supported, 22 model calls and 10 tool requests. Before/after reports and verdicts are saved in `followup.json`. All 23 deterministic check modules passed, including the follow-up tests.

Module 14 live acceptance: thread `20261117T111447_278790Z_71698170` resumed through separate processes at graph counts 2/1, 6/3 and 13/6, preserving budgets and MCP evidence. A completed-thread resume made no new model/tool attempts. All 24 deterministic check modules passed.

Module 15 verification: all 25 deterministic check modules passed. Live Qwen benchmark smoke run `20261117T114856_902731Z_56607cb7` completed one question across retrieval, no-follow-up and follow-up variants. All three passed the seed rubric, with research model calls 1, 13 and 20 respectively. At that smoke-test milestone, the full campaign was still pending; its subsequent completion is recorded below. Independent human label/judge review remains pending.

Subsequently, the full 45-trial campaign completed in `20261117T123834_829810Z_e1629ab5`. Offline successes were 12/15, 13/15 and 15/15; workflow acceptance was 15/15, 12/15 and 13/15 respectively. One offline grade failed index validation. See the [measured comparison and focused review](../evaluation/research_v1_results.md) for discrepancies, execution usage and limitations. Original records are unchanged; independent human review remains pending.
