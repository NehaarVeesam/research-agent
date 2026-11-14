"""Exercise the controller through real MCP with no model API calls."""

import json
import unittest
from unittest.mock import patch

from agent import run_agent
from search import read_source


def tool_request():
    return {
        "content": None,
        "tool_calls": [{
            "id": "call_read_1",
            "type": "function",
            "function": {
                "name": "read_source",
                "arguments": json.dumps({"source_id": "doc_1"}),
            },
        }],
    }


class AgentChecks(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_observation_reaches_model_and_report_is_validated(self):
        calls = 0

        def simulated_model(messages, tools):
            nonlocal calls
            calls += 1
            self.assertEqual(
                {tool["function"]["name"] for tool in tools},
                {"search_sources", "read_source"},
            )
            if calls == 1:
                return tool_request()

            self.assertEqual(messages[-2]["role"], "assistant")
            self.assertEqual(messages[-2]["tool_calls"][0]["id"], "call_read_1")
            self.assertEqual(messages[-1]["role"], "tool")
            self.assertEqual(messages[-1]["tool_call_id"], "call_read_1")
            self.assertEqual(json.loads(messages[-1]["content"]), read_source("doc_1"))
            return {
                "content": json.dumps({
                    "findings": [{
                        "claim": "PaperParse requires ScanBridge for scanned PDFs.",
                        "evidence": [{
                            "source_id": "doc_1",
                            "quote": "Scanned PDFs require the optional ScanBridge OCR integration.",
                        }],
                    }],
                    "evidence_gaps": ["No comparative accuracy benchmark was read."],
                }),
            }

        with patch("agent.call_model", side_effect=simulated_model):
            result = await run_agent("Explain scanned PDF support.")

        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["model_calls"], 2)
        self.assertEqual(result["tool_calls"], 1)
        self.assertEqual(result["checks"]["claim_support"], "not_checked")
        self.assertEqual(result["trace"][0]["transport"], "mcp_stdio")

    async def test_tool_budget_prevents_execution(self):
        with patch("agent.call_model", return_value=tool_request()):
            result = await run_agent("Read a source.", max_tool_calls=0)

        self.assertEqual(result["reason"], "max_tool_calls")
        self.assertEqual(result["trace"], [])

    async def test_model_budget_preserves_completed_tool_result(self):
        with patch("agent.call_model", return_value=tool_request()):
            result = await run_agent("Read a source.", max_model_calls=1)

        self.assertEqual(result["reason"], "max_model_calls")
        self.assertEqual(result["trace"][0]["result"]["source_id"], "doc_1")

    async def test_invalid_final_json_is_rejected(self):
        with patch("agent.call_model", return_value={"content": "not JSON"}):
            result = await run_agent("Produce a report.")

        self.assertEqual(result["status"], "invalid_report")
        self.assertEqual(result["reason"], "schema_validation_failed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
