"""Bounded follow-up scheduling and complete graph regression cases; no Qwen/network."""
import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from mcp import Client
from mcp.server import MCPServer

from app.planning.followup import schedule_followup_node, route_after_followup, finished_followup_history
from app.retrieval.settings import RetrievalSettings
from app.retrieval.web import WebSources
from app.workflow.runner import run_saved_research
from checks.check_web_graph import WebModel
from checks.check_web_retrieval import Response


def state():
    return {"status": "invalid_report", "verify_claims": True, "max_followup_cycles": 1,
        "followup_count": 0, "followup_history": [], "question": "Does Python support async?",
        "model_count": 7, "tool_count": 2, "max_model_calls": 60, "max_tool_calls": 60,
        "tasks": [{"task_id": "task_001", "question": "Does Python support async?",
                   "coverage_criteria": ["Identify async support."], "status": "answered"}],
        "coverage_assessments": {}, "result": {"status": "invalid_report",
            "reason": "claim_support_not_established", "report": {"findings": [
                {"claim": "Python supports async.", "evidence": [{"source_id": "web_1", "quote": "async"}]}],
                "evidence_gaps": []}, "claim_verification": {"status": "complete", "assessments": [
                    {"finding_index": 0, "verdict": "partially_supported", "reason": "Need direct evidence."}]}}}


class SchedulingChecks(unittest.TestCase):
    def test_weak_claim_creates_one_task_preserving_history(self):
        s=state(); original=copy.deepcopy(s);update=schedule_followup_node(s)
        self.assertEqual(s,original)
        self.assertEqual(update["followup_count"],1)
        self.assertEqual(update["tasks"][-1]["task_id"],"followup_001")
        self.assertEqual(update["tasks"][-1]["status"],"pending")
        self.assertEqual(update["followup_history"][0]["before"],s["result"])
        self.assertEqual(update["status"],"running")
        self.assertEqual(route_after_followup(update),"select")

    def test_unresolved_coverage_targets_specific_criterion(self):
        s=state();s["status"]="answered";s["result"]["claim_verification"]["assessments"][0]["verdict"]="supported"
        s["tasks"][0]["status"]="unresolved"
        s["coverage_assessments"]={"task_001":{"criteria":[{"criterion_index":0,"verdict":"not_addressed","rationale":"No direct evidence."}]}}
        u=schedule_followup_node(s)
        target=u["followup_history"][0]["targets"][0]
        self.assertEqual(target["kind"],"coverage")
        self.assertEqual(target["criterion_index"],0)
        self.assertEqual(u["tasks"][0]["status"],"unresolved")

    def test_no_gaps_skips(self):
        s=state();s["status"]="answered";s["result"]["claim_verification"]["assessments"][0]["verdict"]="supported"
        self.assertEqual(schedule_followup_node(s)["followup_decision"]["reason"],"no_actionable_gaps")

    def test_budgets_disabled_and_cycle_cap(self):
        cases=[({"max_model_calls":10},"insufficient_model_budget"),
               ({"max_tool_calls":3},"insufficient_tool_budget"),
               ({"max_followup_cycles":0},"disabled"),({"verify_claims":False},"disabled"),
               ({"followup_count":1},"cycle_limit_reached"),({"max_followup_cycles":2},"invalid_cycle_limit")]
        for fields,reason in cases:
            s=state();s.update(fields);u=schedule_followup_node(s)
            self.assertEqual(u["followup_decision"]["reason"],reason)
            self.assertEqual(route_after_followup(u),"stop")
            self.assertNotIn("status",u)  # Never overwrite the previous failure/outcome.

    def test_invalid_or_incomplete_verification_not_retried(self):
        for status in ("failed","budget_exhausted","invalid_report"):
            s=state();s["status"]=status;s["result"]["reason"]="schema_validation_failed"
            self.assertEqual(schedule_followup_node(s)["followup_decision"]["reason"],"no_valid_assessed_report")
        s=state();s["result"]["claim_verification"]["status"]="incomplete"
        self.assertEqual(schedule_followup_node(s)["followup_decision"]["reason"],"no_valid_assessed_report")

    def test_changed_claim_is_not_automatically_resolved(self):
        s=state();s.update(schedule_followup_node(s))
        s.update(status="answered",result={"status":"answered","report":{"findings":[],"evidence_gaps":["Still missing."]}},model_count=12,tool_count=3)
        history=finished_followup_history(s)
        self.assertEqual(history[0]["original_claim_tracking"][0]["outcome"],"changed_or_removed")
        self.assertEqual(history[0]["phase"],"finished")
        self.assertEqual(history[0]["model_calls_used"],5)
        self.assertEqual(len(s["followup_history"]),1)

    def test_failed_cycle_does_not_claim_original_was_removed(self):
        s=state();s.update(schedule_followup_node(s))
        s.update(status="failed",result={"status":"failed","reason":"synthesis_failed"},model_count=12,tool_count=3)
        record=finished_followup_history(s)[0]
        self.assertEqual(record["original_claim_tracking"][0]["outcome"],"no_updated_report")
        self.assertEqual(record["before"]["report"]["findings"][0]["claim"],"Python supports async.")


class FollowupModel(WebModel):
    def __init__(self, persistent_weak=False, coverage_trigger=False):
        self.verifications=0
        self.persistent_weak=persistent_weak
        self.coverage_trigger=coverage_trigger
        self.followup_searched=False

    def __call__(self,messages,tools):
        system=messages[0]["content"]
        if system.startswith("Verify claim-to-evidence support."):
            self.verifications+=1
            findings=json.loads(messages[-1]["content"])["findings"]
            verdict="partially_supported" if self.persistent_weak or (self.verifications==1 and not self.coverage_trigger) else "supported"
            return {"content":json.dumps({"assessments":[{"finding_index":f["finding_index"],"verdict":verdict,
                "reason":"Controlled verdict for routing verification.","evidence_indices":[0]} for f in findings]})}
        if system.startswith("Assess how well") and self.coverage_trigger and self.verifications==0:
            result=super().__call__(messages,tools)
            value=json.loads(result["content"])
            value["criteria"][0]["verdict"]="partially_addressed"
            return {"content":json.dumps(value)}
        guidance=next((m["content"] for m in messages if m.get("role")=="user" and
                      m.get("content","").startswith("Investigate the following task")),None)
        task=json.loads(guidance.split("\n\n",1)[1]) if guidance else None
        if task and task["task_id"].startswith("followup_"):
            if not self.followup_searched:
                self.followup_searched=True
                return self.tool("search_sources",{"query":"Python async direct support"},"targeted_search")
            result=super().__call__(messages,tools)
            value=json.loads(result["content"])
            value["task_id"]=task["task_id"]
            return {"content":json.dumps(value)}
        return super().__call__(messages,tools)


class CompleteFollowupChecks(unittest.IsolatedAsyncioTestCase):
    async def run_case(self,model,**options):
        session=Mock()
        session.request.return_value=Response(json.dumps({"query":{"search":[{"title":"Python","snippet":"Python language"}]}}).encode())
        session.get.return_value=Response()
        web=WebSources(RetrievalSettings(backend="web"),session)
        server=MCPServer("Follow-up fixture")
        server.tool()(web.search_sources);server.tool()(web.read_source)
        with tempfile.TemporaryDirectory() as root:
            with patch("app.workflow.runner.Client",side_effect=lambda params:Client(server)), \
                 patch("app.retrieval.web.check_public_dns"), \
                 patch.dict("os.environ",{"WEB_SEARCH_PROVIDER":"wikipedia"}):
                result=await run_saved_research("Explain Python async support",model_call=model,
                    research_backend="web",output_dir=Path(root),**options)
            records=json.loads((Path(result["artifacts_dir"])/"followup.json").read_text())
            self.assertEqual(records["cycles_used"],result["followup_count"])
            return result

    async def test_one_cycle_resynthesizes_and_reverifies(self):
        model=FollowupModel();r=await self.run_case(model)
        self.assertEqual(r["status"],"answered")
        self.assertEqual(r["followup_count"],1)
        self.assertEqual(model.verifications,2)
        self.assertTrue(model.followup_searched)
        self.assertEqual(r["model_calls"],12)
        self.assertEqual(r["tool_calls"],3)
        self.assertEqual(r["followup_history"][0]["before"]["status"],"invalid_report")
        self.assertEqual(r["followup_history"][0]["after"]["status"],"answered")

    async def test_persistent_weak_support_stops_without_second_cycle(self):
        model=FollowupModel(persistent_weak=True);r=await self.run_case(model)
        self.assertEqual(r["status"],"invalid_report")
        self.assertEqual(model.verifications,2)
        self.assertEqual(r["followup_decision"]["reason"],"cycle_limit_reached")

    async def test_coverage_can_trigger_followup_after_supported_report(self):
        model=FollowupModel(coverage_trigger=True);r=await self.run_case(model)
        self.assertEqual(r["followup_count"],1)
        self.assertEqual(r["followup_history"][0]["targets"][0]["kind"],"coverage")
        self.assertEqual(r["tasks"][0]["status"],"unresolved")

    async def test_low_budget_preserves_original_report_without_retry(self):
        model=FollowupModel();r=await self.run_case(model,max_model_calls=10)
        self.assertEqual(r["status"],"invalid_report")
        self.assertEqual(r["followup_count"],0)
        self.assertEqual(r["followup_decision"]["reason"],"insufficient_model_budget")

    async def test_explicit_zero_cycles_preserves_baseline(self):
        model=FollowupModel();r=await self.run_case(model,max_followup_cycles=0)
        self.assertEqual(r["followup_count"],0)
        self.assertEqual(r["model_calls"],7)


if __name__=="__main__":unittest.main()
