"""Deterministic external-retrieval checks. No network or model calls."""
import hashlib
import json
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

import requests

from app.retrieval.settings import RetrievalSettings
from app.retrieval.web import WebSources, RetrievalError, canonical_url, check_public_dns, extract_html
from app.workflow.runner import initial_messages, source_inventory
from app.planning.planner import generate_plan


class Response:
    def __init__(self, body=b"<title>Python</title><p>Python supports async functions.</p>", status=200, headers=None):
        self.body = body
        self.status_code = status
        self.headers = headers or {"Content-Type": "text/html"}
        self.encoding = "utf-8"

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def iter_content(self, chunk_size): yield self.body
    def raise_for_status(self):
        if self.status_code >= 400: raise requests.HTTPError("HTTP failure")


class RetrievalChecks(unittest.TestCase):
    def setUp(self):
        self.settings = RetrievalSettings(backend="web")
        self.session = Mock()
        self.web = WebSources(self.settings, self.session)
        self.session.request.return_value = Response(json.dumps({"query": {"search": [
            {"title": "Python (programming language)", "snippet": "<b>Python</b> language"}
        ]}}).encode())
        self.session.get.return_value = Response()

    def discover(self):
        result = self.web.search_sources("Python")
        self.assertNotIn("error", result)
        return result["results"][0]["source_id"]

    def test_discovery_and_ids(self):
        first = self.discover()
        self.assertEqual(first, self.discover())
        self.assertEqual(len(self.web.sources), 1)
        self.assertNotIn("text", self.web.search_sources("Python")["results"][0])
        self.assertFalse(self.session.trust_env)

    @patch("app.retrieval.web.check_public_dns")
    def test_read_metadata_cache_and_inventory(self, dns):
        source_id = self.discover()
        doc = self.web.read_source(source_id)
        self.assertEqual(doc["text"], "Python supports async functions.")
        self.assertEqual(doc["content_hash"], "sha256:" + hashlib.sha256(doc["text"].encode()).hexdigest())
        self.assertIn("retrieved_at", doc)
        self.assertEqual(doc, self.web.read_source(source_id))
        self.session.get.assert_called_once()
        inventory = source_inventory([{"tool": "read_source", "result": doc}])
        self.assertEqual(inventory[source_id]["url"], doc["url"])
        self.assertNotIn("text", inventory[source_id])

    def test_unknown_id_does_not_fetch(self):
        self.assertEqual(self.web.read_source("https://localhost/")["error"], "source_not_found")
        self.session.get.assert_not_called()

    def test_url_policy(self):
        for url in ("http://en.wikipedia.org/a", "https://en.wikipedia.org.evil.test/a",
                    "https://user:pass@en.wikipedia.org/a", "https://en.wikipedia.org:8080/a"):
            with self.subTest(url=url), self.assertRaises(RetrievalError):
                canonical_url(url, self.settings.allowed_domains)
        self.assertEqual(canonical_url("https://en.wikipedia.org/a#b", self.settings.allowed_domains), "https://en.wikipedia.org/a")

    def test_private_dns(self):
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaisesRegex(RetrievalError, "private_address_blocked"):
                check_public_dns("https://en.wikipedia.org/")

    @patch("app.retrieval.web.check_public_dns")
    def test_blocked_redirect(self, dns):
        source_id = self.discover()
        self.session.get.return_value = Response(status=302, headers={"Location": "https://evil.test/"})
        self.assertEqual(self.web.read_source(source_id)["error"], "domain_not_allowed")
        self.session.get.assert_called_once()

    @patch("app.retrieval.web.check_public_dns")
    def test_bounds_types_and_timeouts(self, dns):
        source_id = self.discover()
        cases = [(Response(headers={"Content-Type": "application/pdf"}), "unsupported_content_type"),
                 (Response(b"x" * (self.settings.max_bytes + 1)), "response_too_large"),
                 (Response(status=429), "rate_limited"), (Response(b"<script>hidden</script>"), "empty_page_text")]
        for response, error in cases:
            self.session.get.return_value = response
            self.assertEqual(self.web.read_source(source_id)["error"], error)
        self.session.get.side_effect = requests.Timeout()
        self.assertEqual(self.web.read_source(source_id)["error"], "page_timeout")

    @patch("app.retrieval.web.check_public_dns")
    def test_truncation(self, dns):
        source_id = self.discover()
        self.web.settings = replace(self.settings, max_text_chars=10)
        doc = self.web.read_source(source_id)
        self.assertTrue(doc["truncated"])
        self.assertEqual(len(doc["text"]), 10)

    def test_search_failures(self):
        self.assertEqual(self.web.search_sources("")["error"], "invalid_search_query")
        self.session.request.return_value = Response(b"not json")
        self.assertEqual(self.web.search_sources("test")["error"], "invalid_search_response")
        self.session.request.side_effect = requests.Timeout()
        self.assertEqual(self.web.search_sources("test")["error"], "search_timeout")

    def test_tavily_contract_and_filter(self):
        self.web.settings = replace(self.settings, provider="tavily", tavily_api_key="fake-test-key")
        self.session.request.return_value = Response(json.dumps({"results": [
            {"url": "https://docs.python.org/3/", "title": "Docs", "content": "Python"},
            {"url": "https://unapproved.test/", "title": "Blocked"}
        ]}).encode())
        result = self.web.search_sources("Python")
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["blocked_results"], 1)
        kwargs = self.session.request.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer fake-test-key")
        self.assertFalse(kwargs["json"]["include_answer"])

    def test_extraction(self):
        title, text = extract_html("<title>T</title><nav>Menu</nav><p>A &amp; B</p><script>secret</script>")
        self.assertEqual((title, text), ("T", "A & B"))

    def test_configuration(self):
        with patch.dict("os.environ", {"WEB_SEARCH_PROVIDER": "tavily", "TAVILY_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "TAVILY_API_KEY"):
                RetrievalSettings.from_env("web")
        self.assertNotIn("tavily_api_key", repr(self.settings))
        prompt = initial_messages("Python?", self.settings.context())[0]["content"]
        self.assertIn("Wikipedia", prompt)
        self.assertNotIn("fictional", prompt)


class PlannerContextChecks(unittest.IsolatedAsyncioTestCase):
    async def test_web_planner_context(self):
        def model(messages, tools):
            self.assertIn("Wikipedia", messages[0]["content"])
            self.assertNotIn("three local documents", messages[0]["content"])
            return {"content": json.dumps({"objective": "Investigate Python", "tasks": [
                {"question": "What is Python?", "coverage_criteria": ["Identify the language."]}
            ]})}
        await generate_plan("What is Python?", model, RetrievalSettings(backend="web").context())


if __name__ == "__main__":
    unittest.main()
