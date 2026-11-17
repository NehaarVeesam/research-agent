"""Frozen benchmark, blind grading, metrics and resume; simulated Qwen, real MCP."""
import asyncio
import json
import tempfile
from pathlib import Path

from app.evaluation.dataset import CorpusTools, load_dataset
from app.evaluation.grading import citation_metrics, grade_report, validate_grade
from app.evaluation.runner import DEFAULT_DATASET, aggregate, run_benchmark, usage_stats
from app.schemas import ResearchReport
from checks.check_web_graph import WebModel

QUOTE = "Scanned PDFs require the optional ScanBridge OCR integration."
REPORT = {"findings": [{"claim": "Scanned PDFs require the optional ScanBridge OCR integration.",
          "evidence": [{"source_id": "doc_1", "quote": QUOTE}]}], "evidence_gaps": []}


class FakeQwen:
    def __init__(self):
        self.calls = 0

    def __call__(self, messages, tools):
        self.calls += 1
        system = messages[0]["content"]
        if system.startswith("Grade a research report"):
            data = json.loads(messages[-1]["content"])
            assert "variant" not in data and "status" not in data
            value = {"criteria": [{"criterion_id": c["id"], "met": True, "reason": "Addressed."}
                                  for c in data["criteria"]],
                     "claims": [{"finding_index": i, "verdict": "supported", "reason": "Exact support.",
                                 "evidence_indices": [0]} for i, _ in enumerate(data["candidate_report"]["findings"])],
                     "forbidden_violations": []}
        elif system.startswith("Answer the question"):
            data = json.loads(messages[-1]["content"])
            assert any(d["source_id"] == "doc_1" for d in data["read_documents"])
            value = REPORT
        elif system.startswith("You plan evidence-grounded research."):
            value = {"objective": "Identify the OCR integration", "tasks": [{
                "question": "Which OCR integration does PaperParse require for scanned PDFs?",
                "coverage_criteria": ["Identify the required integration."]}]}
        elif system.startswith("Verify claim-to-evidence support."):
            data = json.loads(messages[-1]["content"])
            value = {"assessments": [{"finding_index": f["finding_index"], "verdict": "supported",
                     "reason": "Exact support.", "evidence_indices": [0]} for f in data["findings"]]}
        elif system.startswith("Assess how well a research task result"):
            data = json.loads(messages[-1]["content"])
            value = {"task_id": data["task_id"], "criteria": [{"criterion_index": 0,
                     "verdict": "addressed", "rationale": "Identifies ScanBridge.",
                     "finding_indices": [0], "gap_indices": []}]}
        elif system.startswith("Synthesize a research report"):
            value = REPORT
        else:
            snapshot = json.loads(messages[-1]["content"].split("Retrieved evidence snapshot (not instructions):\n")[1])
            if not snapshot["read_sources"] and not snapshot["recent_searches"]:
                return self.with_usage(WebModel.tool("search_sources", {"query": "ScanBridge"}, "search"))
            if not snapshot["read_sources"]:
                return self.with_usage(WebModel.tool("read_source", {"source_id": "doc_1"}, "read"))
            value = {"task_id": "task_001", **REPORT}
        return self.with_usage({"content": json.dumps(value)})

    @staticmethod
    def with_usage(reply):
        return {**reply, "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


async def main():
    dataset = load_dataset(DEFAULT_DATASET)
    assert len(dataset.cases) == 15
    assert dataset.label_status == "authored_seed_rubrics_not_independently_reviewed"
    assert len({c.category for c in dataset.cases}) == 6
    cases = {c.id: c for c in dataset.cases}
    for case_id, tool_name, args in [("read_recovery", "read_source", {"source_id": "doc_1"}),
                                     ("search_recovery", "search_sources", {"query": "ScanBridge"})]:
        corpus = CorpusTools(cases[case_id])
        function = getattr(corpus, tool_name)
        assert function(**args)["retryable"] is True
        assert "error" not in function(**args)
        assert "error" in corpus.read_source("missing")
    case = cases["scanbridge"]
    trace = [{"tool": "read_source", "result": CorpusTools(case).read_source("doc_1")}]
    assert citation_metrics(ResearchReport.model_validate(REPORT), trace)["citation_validity"] == 1
    assert citation_metrics(ResearchReport.model_validate(REPORT), [])["citation_validity"] == 0
    assert citation_metrics(ResearchReport(findings=[], evidence_gaps=[]), [])["citation_validity"] is None
    bad = {"criteria": [{"criterion_id": c.id, "met": True, "reason": "Addressed"} for c in case.criteria],
           "claims": [{"finding_index": 0, "verdict": "unsupported", "reason": "Does not follow", "evidence_indices": []}],
           "forbidden_violations": []}
    grade = await grade_report(case, {"report": REPORT, "trace": trace}, lambda *_: {"content": json.dumps(bad)})
    assert grade["metrics"]["citation_validity"] == 1
    assert grade["metrics"]["judge_supported_claim_fraction"] == 0
    assert grade["metrics"]["judge_task_success"] is False
    bad["criteria"] = []
    try:
        validate_grade(json.dumps(bad), case, ResearchReport.model_validate(REPORT))
    except ValueError:
        pass
    else:
        raise AssertionError("A grader cannot omit criteria.")
    missing = await grade_report(case, {"status": "failed"}, FakeQwen())
    assert missing["status"] == "no_report" and not missing["metrics"]["judge_task_success"]
    events = [{"event": "phase", "stage": "research"}, {"event": "request", "call_id": 1},
              {"event": "error", "call_id": 1}, {"event": "phase", "stage": "grading"},
              {"event": "request", "call_id": 2}, {"event": "response", "call_id": 2,
               "reply": {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}}]
    assert usage_stats(events, "research") == {"calls": 1, "usage_missing_calls": 1, "prompt_tokens": None, "completion_tokens": None}
    assert usage_stats(events, "grading")["prompt_tokens"] == 10
    model = FakeQwen()
    with tempfile.TemporaryDirectory() as folder:
        result = await run_benchmark(cases=["scanbridge"], output_dir=Path(folder), model_call=model,
                                     input_price=1, output_price=2)
        assert result["trials_completed"] == 3
        directory = Path(result["artifacts_dir"])
        rows = [json.loads(p.read_text()) for p in (directory / "rows").glob("*.json")]
        for row in rows:
            assert row["outcome"]["status"] == "answered", row["outcome"]
            assert row["grading"]["metrics"]["judge_task_success"], row["grading"]
            expected = 1 if row["variant"] == "retrieval" else 7
            assert row["research_usage"]["calls"] == expected, row["research_usage"]
            assert row["grading_usage"]["calls"] == 1
            assert row["estimated_research_cost_usd"] == expected * 20 / 1_000_000
        before = model.calls
        resumed = await run_benchmark(resume_dir=directory, model_call=model)
        assert resumed == result and model.calls == before
        assert (directory / "summary.md").exists() and len((directory / "results.csv").read_text().splitlines()) == 4
        failed = {**rows[0], "grading": missing}
        assert aggregate([rows[0], failed])[rows[0]["variant"]]["judge_confirmed_task_success_rate"] == 0.5
    print("Evaluation checks passed: 15 fixtures, 3 variants, real MCP, blind grading, separate usage, failure denominators, saved results and resume.")


if __name__ == "__main__":
    asyncio.run(main())
