"""Saved-run checks using controlled responses; no endpoint requests."""
import asyncio
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.workflow.artifacts import RunArtifacts
from app.workflow.runner import run_saved_research


class ArtifactChecks(unittest.TestCase):
    def test_model_recording_and_redaction(self):
        with tempfile.TemporaryDirectory() as root:
            artifacts = RunArtifacts(Path(root), secrets=("test-secret",))
            recorded = artifacts.record_model(lambda messages, tools: {"content": "test-secret"})
            with artifacts.capture_logs():
                logging.getLogger("app.workflow.nodes").info("Hidden test-secret")
                self.assertEqual(recorded([], []), {"content": "test-secret"})
            content = (artifacts.directory / "model_calls.jsonl").read_text()
            self.assertNotIn("test-secret", content)
            self.assertEqual([json.loads(line)["event"] for line in content.splitlines()], ["request", "response"])
            self.assertNotIn("test-secret", (artifacts.directory / "run.log").read_text())

    def test_failed_model_recorded(self):
        with tempfile.TemporaryDirectory() as root:
            artifacts = RunArtifacts(Path(root))
            def failing(messages, tools):
                raise ConnectionError("Connection refused")
            with self.assertRaises(ConnectionError):
                artifacts.record_model(failing)([], [])
            events = [json.loads(line) for line in (artifacts.directory / "model_calls.jsonl").read_text().splitlines()]
            self.assertEqual(events[-1]["event"], "error")


class SavedRunChecks(unittest.IsolatedAsyncioTestCase):
    async def run_case(self, response=None, error=None):
        with tempfile.TemporaryDirectory() as root:
            with patch("app.workflow.runner.run_graph_agent", return_value=response, side_effect=error):
                result = await run_saved_research("Test question", output_dir=Path(root), research_backend="local")
            directory = Path(result["artifacts_dir"])
            saved = json.loads((directory / "result.json").read_text())
            metadata = json.loads((directory / "run.json").read_text())
            self.assertEqual(saved, result)
            self.assertEqual(metadata["model_provider"], "qwen")
            self.assertEqual(metadata["status"], result["status"])
            self.assertIn("finished_at", metadata)
            self.assertTrue((directory / "run.log").exists())
            self.assertEqual(json.loads((directory / "trace.json").read_text()), result.get("trace", []))
            return result

    async def test_success(self):
        result = await self.run_case({"status": "answered", "model_calls": 2, "tool_calls": 1,
                                      "trace": [{"tool": "read_source", "result": {"source_id": "doc_1"}}]})
        self.assertEqual(result["status"], "answered")

    async def test_handled_failure(self):
        result = await self.run_case({"status": "failed", "reason": "planning_failed", "trace": [], "model_calls": 1})
        self.assertEqual(result["reason"], "planning_failed")

    async def test_unexpected_failure(self):
        result = await self.run_case(error=ConnectionError("MCP startup failed"))
        self.assertEqual(result["reason"], "unhandled_run_error")

    async def test_cancelled_run(self):
        result = await self.run_case(error=asyncio.CancelledError())
        self.assertEqual(result["reason"], "run_cancelled")


if __name__ == "__main__":
    unittest.main()
