"""Full graph + real in-process MCP, mocked external HTTP, simulated model."""
import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from mcp import Client
from mcp.server import MCPServer

from app.retrieval.settings import RetrievalSettings
from app.retrieval.web import WebSources
from app.workflow.runner import run_saved_research
from checks.check_web_retrieval import Response


class WebModel:
    def __call__(self, messages, tools):
        system = messages[0]["content"]
        if system.startswith("Verify claim-to-evidence support."):
            data = json.loads(messages[-1]["content"])
            value = {"assessments": [{"finding_index": finding["finding_index"],
                       "verdict": "supported", "reason": "The cited text directly supports async support.",
                       "evidence_indices": [0]} for finding in data["findings"]]}
        elif system.startswith("You plan evidence-grounded research."):
            assert "Wikipedia" in system
            value = {"objective": "Explain Python async support", "tasks": [{
                "question": "Does Python support async functions?",
                "coverage_criteria": ["Identify async function support."]}]}
        elif system.startswith("Assess how well a research task result"):
            data = json.loads(messages[-1]["content"])
            value = {"task_id": data["task_id"], "criteria": [{"criterion_index": 0,
                "verdict": "addressed", "rationale": "Finding directly addresses support.",
                "finding_indices": [0], "gap_indices": []}]}
        elif system.startswith("Synthesize a research report"):
            data = json.loads(messages[-1]["content"])
            value = {"findings": [f for r in data["task_results"].values() for f in r["findings"]],
                     "evidence_gaps": []}
        else:
            assert "Wikipedia" in system and "fictional" not in system
            snapshot = json.loads(messages[-1]["content"].split("Retrieved evidence snapshot (not instructions):\n")[1])
            if not snapshot["read_sources"] and not snapshot["recent_searches"]:
                return self.tool("search_sources", {"query": "Python async"}, "search")
            if not snapshot["read_sources"]:
                return self.tool("read_source", {"source_id": snapshot["recent_searches"][-1]["result"]["results"][0]["source_id"]}, "read")
            results = [{**snapshot["read_sources"][0], "text": snapshot["read_sources"][0]["passages"]}]
            source = results[-1]
            value = {"task_id": "task_001", "findings": [{
                "claim": "Python supports async functions.", "evidence": [{
                    "source_id": source["source_id"], "quote": source["text"]}]}], "evidence_gaps": []}
        return {"content": json.dumps(value)}

    @staticmethod
    def tool(name, arguments, call_id):
        return {"content": None, "tool_calls": [{"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)}}]}


async def main():
    session = Mock()
    session.request.return_value = Response(json.dumps({"query": {"search": [
        {"title": "Python", "snippet": "Python language"}]}}).encode())
    session.get.return_value = Response()
    web = WebSources(RetrievalSettings(backend="web"), session)
    server = MCPServer("Mock external sources")
    server.tool()(web.search_sources)
    server.tool()(web.read_source)
    with patch("app.workflow.runner.Client", side_effect=lambda parameters: Client(server)), \
         patch("app.retrieval.web.check_public_dns"), \
         patch.dict("os.environ", {"WEB_SEARCH_PROVIDER": "wikipedia"}), \
         tempfile.TemporaryDirectory() as records:
        result = await run_saved_research("Explain Python async support", model_call=WebModel(),
                                          research_backend="web", output_dir=Path(records))
        directory = Path(result["artifacts_dir"])
        assert json.loads((directory / "result.json").read_text()) == result
        assert len((directory / "model_calls.jsonl").read_text().splitlines()) == 14
        assert "Research finished: answered" in (directory / "run.log").read_text()
    assert result["status"] == "answered", result
    assert result["model_calls"] == 7, result["model_calls"]
    assert result["tool_calls"] == 2
    assert result["checks"]["claim_support"] == "passed"
    assert result["claim_verification"]["status"] == "complete"
    assert len(result["sources"]) == 1
    source = next(iter(result["sources"].values()))
    assert source["url"] == "https://en.wikipedia.org/wiki/Python"
    assert source["content_hash"].startswith("sha256:")
    print("Web graph passed: planning → MCP search/read → task → coverage → synthesis → validation.")
    print("7 simulated model calls, 2 MCP tools, 1 source with provenance; no network or Qwen.")


if __name__ == "__main__":
    asyncio.run(main())
