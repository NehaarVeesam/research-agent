"""Complete task workflow checks: simulated model, real local MCP, no Qwen."""

import json
import unittest

from app.workflow.runner import run_graph_agent


class SimulatedModel:
    def __init__(self, task_count=1, invalid_task=False, invalid_assessment=False,
                 invalid_synthesis=False, malformed_task_json=False,
                 malformed_repair=False, invalid_repair_quote=False,
                 repair_requests_tools=False):
        self.task_count = task_count
        self.invalid_task = invalid_task
        self.invalid_assessment = invalid_assessment
        self.invalid_synthesis = invalid_synthesis
        self.malformed_task_json = malformed_task_json
        self.malformed_repair = malformed_repair
        self.invalid_repair_quote = invalid_repair_quote
        self.repair_requests_tools = repair_requests_tools
        self.pending_repair = None
        self.phases = []

    @staticmethod
    def response(value):
        return {"content": json.dumps(value)}

    def __call__(self, messages, tools):
        instructions = messages[0]["content"]

        if instructions.startswith("Repair the formatting of a research task result."):
            self.phases.append("repair")
            assert tools == []
            data = json.loads(messages[-1]["content"])
            assert data["rejected_response"].startswith("All searches")
            assert "json_invalid" in data["validation_error"]
            if self.repair_requests_tools:
                return {"content": None, "tool_calls": [{"id": "forbidden_repair_tool"}]}
            if self.malformed_repair:
                return {"content": "Still not valid JSON."}
            repaired = json.loads(json.dumps(self.pending_repair))
            if self.invalid_repair_quote:
                repaired["findings"][0]["evidence"][0]["quote"] = "Invented quotation."
            return self.response(repaired)

        if instructions.startswith("You plan evidence-grounded research."):
            self.phases.append("plan")
            assert tools == []
            tasks = [{
                "question": "What OCR integration does PaperParse require?",
                "coverage_criteria": ["Identify the required OCR integration."],
            }, {
                "question": "What quantitative accuracy is documented?",
                "coverage_criteria": ["Provide a documented accuracy measurement."],
            }]
            return self.response({
                "objective": "Investigate PaperParse support and evidence gaps.",
                "tasks": tasks[:self.task_count],
            })

        if instructions.startswith("Assess how well a research task result"):
            self.phases.append("assess")
            assert tools == []
            data = json.loads(messages[-1]["content"])
            if self.invalid_assessment:
                return self.response({"task_id": data["task_id"], "criteria": []})
            supported = bool(data["findings"])
            return self.response({
                "task_id": data["task_id"],
                "criteria": [{
                    "criterion_index": 0,
                    "verdict": "addressed" if supported else "not_addressed",
                    "rationale": (
                        "Finding 0 identifies the integration." if supported
                        else "No accuracy measurement was found."
                    ),
                    "finding_indices": [0] if supported else [],
                    "gap_indices": [] if supported else [0],
                }],
            })

        if instructions.startswith("Synthesize a research report"):
            self.phases.append("synthesize")
            assert tools == []
            if self.invalid_synthesis:
                return {"content": "not JSON"}
            data = json.loads(messages[-1]["content"])
            assert all(t["status"] in {"answered", "unresolved"} for t in data["tasks"])
            assert len(data["task_results"]) == self.task_count
            assert len(data["coverage_assessments"]) == self.task_count
            return self.response({
                "findings": [
                    finding for result in data["task_results"].values()
                    for finding in result["findings"]
                ],
                "evidence_gaps": [
                    gap for result in data["task_results"].values()
                    for gap in result["evidence_gaps"]
                ],
            })

        self.phases.append("research")
        assert {tool["function"]["name"] for tool in tools} == {
            "search_sources", "read_source",
        }
        # Find the most recent task-selection message in the conversation.
        guidance = next(
            message["content"] for message in reversed(messages)
            if message["role"] == "user"
            and message["content"].startswith("Investigate the following task")
        )
        task = json.loads(guidance.split("\n\n", 1)[1])
        task_id = task["task_id"]

        if task_id == "task_001" and messages[-1]["role"] != "tool":
            return {
                "content": None,
                "tool_calls": [{
                    "id": "read_1",
                    "type": "function",
                    "function": {
                        "name": "read_source",
                        "arguments": '{"source_id": "doc_1"}',
                    },
                }],
            }

        if task_id == "task_001":
            assert messages[-2]["tool_calls"][0]["id"] == "read_1"
            assert messages[-1]["tool_call_id"] == "read_1"
            assert json.loads(messages[-1]["content"])["source_id"] == "doc_1"
            findings = [{
                "claim": "PaperParse requires ScanBridge for scanned PDFs.",
                "evidence": [{
                    "source_id": "doc_1",
                    "quote": "Scanned PDFs require the optional ScanBridge OCR integration.",
                }],
            }]
        else:
            findings = []

        task_result = {
            "task_id": "wrong_task" if self.invalid_task else task_id,
            "findings": findings,
            "evidence_gaps": [] if findings else [
                "No quantitative accuracy measurement was collected."
            ],
        }
        if self.malformed_task_json:
            self.pending_repair = task_result
            return {"content": "All searches return the same documents.\n\n" + json.dumps(task_result)}
        return self.response(task_result)


class GraphAgentChecks(unittest.IsolatedAsyncioTestCase):
    async def run_case(self, model=None, **budgets):
        model = model or SimulatedModel()
        result = await run_graph_agent(
            "Investigate PaperParse capabilities and accuracy evidence.",
            model_call=model,
            verify_claims=False,
            **budgets,
        )
        self.assertEqual(result["model_calls"], len(model.phases))
        return result, model

    async def test_single_task_complete_path(self):
        result, model = await self.run_case()
        self.assertEqual(result["status"], "answered")
        self.assertEqual(model.phases, ["plan", "research", "research", "assess", "synthesize"])
        self.assertEqual(result["model_calls"], 5)
        self.assertEqual(result["tool_calls"], 1)
        self.assertEqual(result["tasks"][0]["status"], "answered")
        self.assertIn("task_001", result["task_results"])
        self.assertIn("task_001", result["coverage_assessments"])
        self.assertEqual(result["checks"]["claim_support"], "not_checked")

    async def test_multiple_tasks_preserve_unresolved_result(self):
        result, model = await self.run_case(SimulatedModel(task_count=2))
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["model_calls"], 7)
        self.assertEqual([t["status"] for t in result["tasks"]], ["answered", "unresolved"])
        self.assertEqual(set(result["task_results"]), {"task_001", "task_002"})
        self.assertEqual(set(result["coverage_assessments"]), {"task_001", "task_002"})
        self.assertTrue(result["report"]["evidence_gaps"])
        self.assertEqual(model.phases[-1], "synthesize")

    async def test_model_budget_before_research(self):
        result, model = await self.run_case(max_model_calls=1)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(model.phases, ["plan"])
        self.assertEqual(result["trace"], [])

    async def test_budget_before_assessment_preserves_result(self):
        result, model = await self.run_case(max_model_calls=3)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertIn("task_001", result["task_results"])
        self.assertEqual(result["coverage_assessments"], {})
        self.assertNotIn("assess", model.phases)

    async def test_budget_before_synthesis_preserves_assessment(self):
        result, model = await self.run_case(max_model_calls=4)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertIn("task_001", result["coverage_assessments"])
        self.assertNotIn("synthesize", model.phases)

    async def test_tool_budget_blocks_execution(self):
        result, _ = await self.run_case(max_tool_calls=0)
        self.assertEqual(result["reason"], "max_tool_calls")
        self.assertEqual(result["tool_calls"], 0)
        self.assertEqual(result["trace"], [])

    async def test_wrong_task_result_is_rejected(self):
        result, model = await self.run_case(SimulatedModel(invalid_task=True))
        self.assertEqual(result["reason"], "task_result_validation_failed")
        self.assertNotIn("assess", model.phases)
        self.assertNotIn("repair", model.phases)

    async def test_json_repair_continues_to_assessment_and_synthesis(self):
        result, model = await self.run_case(SimulatedModel(malformed_task_json=True))
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["model_calls"], 6)
        self.assertEqual(model.phases.count("repair"), 1)
        self.assertEqual(result["task_repair_attempts"], {"task_001": 1})
        self.assertIn("task_001", result["task_results"])
        self.assertEqual(model.phases[-2:], ["assess", "synthesize"])

    async def test_each_task_has_its_own_repair_limit(self):
        result, model = await self.run_case(SimulatedModel(task_count=2, malformed_task_json=True))
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["model_calls"], 9)
        self.assertEqual(model.phases.count("repair"), 2)
        self.assertEqual(result["task_repair_attempts"], {"task_001": 1, "task_002": 1})

    async def test_repeated_invalid_json_stops_after_one_repair(self):
        result, model = await self.run_case(SimulatedModel(malformed_task_json=True, malformed_repair=True))
        self.assertEqual(result["status"], "invalid_report")
        self.assertEqual(result["reason"], "task_result_validation_failed")
        self.assertEqual(result["model_calls"], 4)
        self.assertEqual(model.phases.count("repair"), 1)
        self.assertEqual(result["task_results"], {})
        self.assertNotIn("assess", model.phases)

    async def test_no_budget_prevents_repair_request(self):
        result, model = await self.run_case(SimulatedModel(malformed_task_json=True), max_model_calls=3)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["task_repair_attempts"], {})
        self.assertIn("validation_error", result)
        self.assertNotIn("repair", model.phases)

    async def test_repaired_json_does_not_bypass_quote_validation(self):
        result, model = await self.run_case(SimulatedModel(malformed_task_json=True, invalid_repair_quote=True))
        self.assertEqual(result["status"], "invalid_report")
        self.assertFalse(result["repairable"])
        self.assertIn("quote does not occur", result["error"])
        self.assertEqual(model.phases.count("repair"), 1)
        self.assertNotIn("assess", model.phases)

    async def test_repair_tool_requests_are_rejected(self):
        result, model = await self.run_case(SimulatedModel(malformed_task_json=True, repair_requests_tools=True))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "task_result_repair_failed")
        self.assertEqual(result["tool_calls"], 1)
        self.assertEqual(result["task_repair_attempts"], {"task_001": 1})
        self.assertNotIn("assess", model.phases)

    async def test_invalid_assessment_stops_before_synthesis(self):
        result, model = await self.run_case(SimulatedModel(invalid_assessment=True))
        self.assertEqual(result["reason"], "coverage_assessment_failed")
        self.assertNotIn("synthesize", model.phases)

    async def test_invalid_synthesis_is_rejected(self):
        result, _ = await self.run_case(SimulatedModel(invalid_synthesis=True))
        self.assertEqual(result["reason"], "schema_validation_failed")
        self.assertIn("task_001", result["coverage_assessments"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
