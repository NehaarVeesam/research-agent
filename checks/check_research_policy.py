"""Regression checks for real-run failure modes; no network or Qwen."""
import json
import unittest
from unittest.mock import patch, Mock, AsyncMock
from app.workflow.research_policy import scope_plan, relevant_passages, web_messages
from app.workflow.nodes import make_model_node, collect_task_result_node, make_task_repair_node, select_task_node, make_tool_node
from app.agent import call_model


def state():
    task = {"task_id": "task_001", "question": "What is yield?", "coverage_criteria": ["Explain yield."], "status": "in_progress"}
    return {"bounded_web": True, "question": "What is yield?", "research_context": "Wikipedia articles only",
        "tasks": [task], "active_task_id": "task_001", "model_count": 1, "tool_count": 0,
        "max_model_calls": 60, "max_tool_calls": 60, "status": "running", "result": None,
        "messages": [{"role": "system", "content": "Return task JSON."}, {"role": "user", "content":
        "Investigate the following task\n\n" + json.dumps(task)}], "trace": [], "latest_reply": None}


class PolicyChecks(unittest.TestCase):
    def test_scope(self):
        plan = {"objective": "Explain Python", "tasks": [{"question": "What does official Python documentation say?",
                "coverage_criteria": ["Primary documentation explains yield."]}]}
        updated, adjustments = scope_plan(plan, "Wikipedia articles only")
        self.assertEqual(len(adjustments), 2)
        self.assertNotIn("official", updated["tasks"][0]["question"])
        self.assertEqual(plan["tasks"][0]["coverage_criteria"][0], "Primary documentation explains yield.")

    def test_bounded_exact_passages(self):
        text = "unrelated text. " * 10000 + "yield suspends execution. " * 100
        passages = relevant_passages(text, "yield suspends execution", 5000)
        self.assertLessEqual(len(passages), 5000)
        self.assertIn("yield suspends execution", passages)
        for passage in passages.split("\n\n[passage boundary]\n\n"):
            self.assertIn(passage, text)

    def test_request_configuration(self):
        response = Mock()
        response.json.return_value = {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}], "usage": {"total_tokens": 5}}
        with patch("app.agent.requests.post", return_value=response) as post:
            result = call_model([{"role": "user", "content": "JSON"}], [])
        payload = post.call_args.kwargs["json"]
        self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(payload["response_format"]["type"], "json_object")
        self.assertEqual(result["finish_reason"], "stop")


class AsyncPolicyChecks(unittest.IsolatedAsyncioTestCase):
    async def test_force_conclusion(self):
        s = state(); s["task_model_counts"] = {"task_001": 3}
        def model(messages, tools):
            self.assertEqual(tools, [])
            self.assertIn("Tools are disabled", messages[-1]["content"])
            return {"content": json.dumps({"task_id": "task_001", "findings": [], "evidence_gaps": ["No evidence."]})}
        result = await make_model_node(model, [{"type": "function"}])(s)
        self.assertEqual(result["task_model_counts"]["task_001"], 4)

    async def test_empty_response_retry_excludes_reasoning(self):
        s=state(); s["latest_reply"]={"content": None, "reasoning": "DO NOT USE REASONING AS EVIDENCE"}
        update=collect_task_result_node(s); s.update(update)
        self.assertTrue(s["result"]["repairable"])
        def model(messages, tools):
            self.assertNotIn("DO NOT USE REASONING", str(messages))
            self.assertEqual(tools, [])
            return {"content": '{"task_id":"task_001","findings":[],"evidence_gaps":["No evidence."]}'}
        s.update(await make_task_repair_node(model)(s))
        self.assertIn("task_results", collect_task_result_node(s))
        self.assertEqual(s["task_repair_attempts"]["task_001"], 1)

    async def test_search_allowance_blocks_external_call(self):
        s=state()
        s["trace"] = [{"task_id": "task_001", "tool": "search_sources", "arguments": json.dumps({"query": str(i)}),
                       "result": {"results": []}} for i in range(2)]
        s["latest_reply"] = {"tool_calls": [{"id": "blocked", "function": {"name": "search_sources",
                                      "arguments": '{"query":"another search"}'}}]}
        with patch("app.workflow.nodes.execute_mcp_tool", new_callable=AsyncMock) as execute:
            update = await make_tool_node(None)(s)
        execute.assert_not_awaited()
        self.assertEqual(update["trace"][0]["result"]["error"], "task_research_allowance_reached")
        self.assertEqual(len(update["messages"]), 1)
        self.assertEqual(update["messages"][0]["tool_call_id"], "blocked")

    async def test_reserve_synthesis(self):
        s=state(); s["model_count"]=58
        update=select_task_node(s)
        self.assertIsNone(update["active_task_id"])
        self.assertEqual(update["tasks"][0]["status"], "unresolved")
        self.assertEqual(update["task_results"]["task_001"]["findings"], [])


if __name__ == "__main__": unittest.main()
