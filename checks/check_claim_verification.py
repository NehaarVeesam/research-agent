"""Claim verification acceptance and failure checks. No network/model endpoint."""
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock

from app.schemas import ResearchReport
from app.verification.claims import validate_assessments, verification_messages
from app.verification.node import make_claim_verification_node
from app.workflow.research_policy import completion_reserve


def report(claim="Scans require OCR."):
    return ResearchReport.model_validate({"findings": [{"claim": claim, "evidence": [
        {"source_id": "doc_1", "quote": "Scans require OCR."}]}], "evidence_gaps": []})


def trace():
    return [{"tool": "read_source", "result": {"source_id": "doc_1", "title": "Test",
             "text": "Digital PDFs use embedded text. Scans require OCR. No accuracy benchmark exists."}}]


def response(verdict="supported", index=0, evidence=None):
    return {"content": json.dumps({"assessments": [{"finding_index": index,
        "verdict": verdict, "reason": "Assess the cited passage, not assumed truth.",
        "evidence_indices": [0] if evidence is None else evidence}]})}


def state(r=None, limit=8):
    return {"status": "answered", "model_count": 0, "max_model_calls": limit, "trace": trace(),
        "verify_claims": True, "result": {"status": "answered", "report": (r or report()).model_dump(),
            "checks": {"schema": "passed", "evidence_references": "passed", "claim_support": "not_checked"}}}


class SchemaChecks(unittest.TestCase):
    def test_missing_duplicate_and_wrong_indices(self):
        item=json.loads(response()["content"])["assessments"][0]
        for items in ([], [item, item], [{**item, "finding_index": 1}], [{**item, "evidence_indices": [2]}],
                      [{**item, "evidence_indices": [0, 0]}], [{**item, "evidence_indices": []}]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                validate_assessments(json.dumps({"assessments": items}), report(), [0])

    def test_wrong_quote_stops_before_model(self):
        r=report();r.findings[0].evidence[0].quote="Invented quote."
        with self.assertRaisesRegex(ValueError,"Verify source reads"):
            verification_messages(r, trace(), [0])

    def test_context_is_supplied(self):
        messages=verification_messages(report(), trace(), [0])
        payload=json.loads(messages[1]["content"])
        self.assertIn("No accuracy benchmark",payload["findings"][0]["evidence"][0]["nearby_context"])
        self.assertIn("untrusted",messages[0]["content"])

    def test_reserve_accounts_for_verification(self):
        s={"verify_claims": True,"tasks": [{"task_id":"t1","status":"pending"}], "task_results":{}}
        self.assertEqual(completion_reserve(s),3)


class NodeChecks(unittest.IsolatedAsyncioTestCase):
    async def test_supported(self):
        update=await make_claim_verification_node(lambda m,t:response())(state())
        self.assertEqual(update["status"],"answered")
        self.assertEqual(update["result"]["checks"]["claim_support"],"passed")
        self.assertEqual(update["model_count"],1)

    async def test_partial_and_unsupported_retain_report(self):
        for verdict in ("partially_supported", "unsupported"):
            s=state(report("The tool achieves 99% OCR accuracy."))
            update=await make_claim_verification_node(lambda m,t:response(verdict))(s)
            self.assertEqual(update["status"],"invalid_report")
            self.assertEqual(update["result"]["report"],s["result"]["report"])
            self.assertEqual(update["result"]["checks"]["claim_support"],"needs_review")

    async def test_budget_exhaustion(self):
        model=Mock()
        update=await make_claim_verification_node(model)(state(limit=0))
        model.assert_not_called()
        self.assertEqual(update["status"],"budget_exhausted")
        self.assertEqual(update["result"]["claim_verification"]["status"],"incomplete")

    async def test_empty_invalid_and_tool_reply_fail_closed(self):
        for reply in ({"content":None,"reasoning":"supported"},{"content":"not JSON"},
                      {"tool_calls":[{"id":"forbidden"}]}, {"content":'{"assessments":[]}'}):
            update=await make_claim_verification_node(lambda m,t:reply)(state())
            self.assertEqual(update["status"],"failed")
            self.assertEqual(update["model_count"],1)

    async def test_empty_report_not_vacuously_verified(self):
        s=state();s["result"]["report"]={"findings":[],"evidence_gaps":["No evidence."]}
        model=Mock();update=await make_claim_verification_node(model)(s)
        model.assert_not_called()
        self.assertEqual(update["result"]["checks"]["claim_support"],"not_applicable")

    async def test_failed_reference_validation_skips_model(self):
        s=state();s["trace"]=[];model=Mock()
        update=await make_claim_verification_node(model)(s)
        model.assert_not_called()
        self.assertEqual(update["status"],"invalid_report")

    async def test_batch_budget_preserves_completed_assessments(self):
        r=report();r.findings=r.findings*5;s=state(r,limit=1)
        def model(messages,tools):
            data=json.loads(messages[-1]["content"])
            return {"content":json.dumps({"assessments":[{"finding_index":f["finding_index"],
                "verdict":"supported","reason":"Direct support.","evidence_indices":[0]} for f in data["findings"]]})}
        update=await make_claim_verification_node(model)(s)
        self.assertEqual(update["status"],"budget_exhausted")
        self.assertEqual(len(update["result"]["claim_verification"]["assessments"]),4)

    async def test_disabled_or_invalid_report_skips(self):
        for s in (dict(state(),verify_claims=False),dict(state(),status="invalid_report")):
            model=Mock();self.assertEqual(await make_claim_verification_node(model)(s),{})
            model.assert_not_called()


class SavedVerificationChecks(unittest.IsolatedAsyncioTestCase):
    async def test_replay_preserves_input_and_saves_verdicts(self):
        from app.verification.runner import verify_saved_report
        with tempfile.TemporaryDirectory() as root:
            original = Path(root) / "original"; original.mkdir()
            data = {"report": report().model_dump(), "trace": trace(), "run_id": "source-run"}
            raw = json.dumps(data)
            (original / "result.json").write_text(raw)
            result = await verify_saved_report(original, Path(root) / "records",
                                               model_call=lambda m,t: response())
            self.assertEqual(result["status"], "answered")
            self.assertEqual((original / "result.json").read_text(), raw)
            directory = Path(result["artifacts_dir"])
            self.assertEqual(json.loads((directory / "claim_verification.json").read_text())["status"], "complete")
            self.assertEqual(len((directory / "model_calls.jsonl").read_text().splitlines()), 2)
            self.assertEqual(result["source_run_id"], "source-run")

    async def test_replay_rejects_unread_citation_without_model_call(self):
        from app.verification.runner import verify_saved_report
        with tempfile.TemporaryDirectory() as root:
            original = Path(root) / "original"; original.mkdir()
            (original / "result.json").write_text(json.dumps({"report": report().model_dump(), "trace": []}))
            model=Mock()
            result=await verify_saved_report(original, Path(root) / "records", model_call=model)
            model.assert_not_called()
            self.assertEqual(result["status"], "invalid_report")


if __name__ == "__main__":unittest.main()
