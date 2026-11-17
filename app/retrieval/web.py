"""Bounded external discovery and retrieval; source registry lasts one server run."""

import hashlib
import ipaddress
import json
import re
import socket
import copy
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote, urldefrag, urljoin, urlsplit, urlunsplit

import requests

from app.retrieval.settings import RetrievalSettings


class RetrievalError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class TextExtractor(HTMLParser):
    """Small deterministic extractor, not a JavaScript renderer or readability engine."""
    IGNORED = {"script", "style", "noscript", "nav", "footer", "header", "aside", "svg", "form", "template"}
    BLOCKS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.title_parts = []
        self.hidden = 0
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORED:
            self.hidden += 1
        if tag == "title":
            self.in_title = True
        if not self.hidden and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.IGNORED and self.hidden:
            self.hidden -= 1
        if tag == "title":
            self.in_title = False
        if not self.hidden and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        elif not self.hidden:
            self.parts.append(data)

    def text(self):
        return "\n".join(
            line for line in (re.sub(r"\s+", " ", x).strip() for x in "".join(self.parts).splitlines())
            if line
        )


def extract_html(html):
    parser = TextExtractor()
    parser.feed(html)
    return " ".join(parser.title_parts).strip(), parser.text()


def canonical_url(url, domains):
    try:
        parts = urlsplit(urldefrag(url)[0])
        host = (parts.hostname or "").lower().rstrip(".")
        if parts.scheme != "https" or not host or parts.username or parts.password:
            raise RetrievalError("url_not_permitted")
        if parts.port not in (None, 443):
            raise RetrievalError("url_not_permitted")
        if not any(host == domain or host.endswith("." + domain) for domain in domains):
            raise RetrievalError("domain_not_allowed")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            if not address.is_global:
                raise RetrievalError("private_address_blocked")
        return urlunsplit(("https", host, parts.path or "/", parts.query, ""))
    except (TypeError, ValueError) as exc:
        if isinstance(exc, RetrievalError):
            raise
        raise RetrievalError("invalid_url") from exc


def check_public_dns(url):
    host = urlsplit(url).hostname
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise RetrievalError("dns_failed") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise RetrievalError("private_address_blocked")


class WebSources:
    def __init__(self, settings: RetrievalSettings, session=None, store_path=None):
        self.settings = settings
        self.session = session or requests.Session()
        # Do not inherit proxy settings or .netrc credentials for arbitrary pages.
        self.session.trust_env = False
        self.sources = {}
        self.cache = {}
        self.queries = {}
        self.store_path = Path(store_path) if store_path else None
        if self.store_path and self.store_path.exists():
            data = json.loads(self.store_path.read_text())
            if data.get("version") != 1:
                raise ValueError("Unsupported source-store version.")
            for source_id, source in data["sources"].items():
                url = canonical_url(source["url"], settings.allowed_domains)
                if source_id != "web_" + hashlib.sha256(url.encode()).hexdigest()[:24]:
                    raise ValueError("Source-store ID does not match its URL.")
            for source_id, document in data["cache"].items():
                if source_id not in data["sources"] or document["source_id"] != source_id:
                    raise ValueError("Invalid cached source ID.")
                if document["content_hash"] != "sha256:" + hashlib.sha256(document["text"].encode()).hexdigest():
                    raise ValueError("Cached source text hash mismatch.")
            self.sources, self.cache = data["sources"], data["cache"]
            self.queries = data.get("queries", {})

    def _save(self):
        if self.store_path:
            temporary = self.store_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"version": 1, "sources": self.sources,
                "cache": self.cache, "queries": self.queries}), encoding="utf-8")
            temporary.replace(self.store_path)

    def _body(self, response):
        content = bytearray()
        for chunk in response.iter_content(chunk_size=16_384):
            content.extend(chunk)
            if len(content) > self.settings.max_bytes:
                raise RetrievalError("response_too_large")
        return bytes(content)

    def _json_request(self, method, url, **kwargs):
        with self.session.request(
            method, url, timeout=(5, self.settings.timeout),
            allow_redirects=False, stream=True, **kwargs,
        ) as response:
            if response.status_code == 429:
                raise RetrievalError("rate_limited")
            response.raise_for_status()
            if response.status_code != 200:
                raise RetrievalError("search_http_error")
            return json.loads(self._body(response))

    def _search(self, query):
        if self.settings.provider == "wikipedia":
            data = self._json_request(
                "GET", "https://en.wikipedia.org/w/api.php",
                headers={"User-Agent": "ResearchAgentLearningProject/0.1"},
                params={"action": "query", "list": "search", "srsearch": query,
                        "srlimit": self.settings.max_results, "format": "json", "formatversion": 2},
            )
            if "error" in data:
                raise RetrievalError("search_provider_error")
            return [
                {"title": item["title"], "url": "https://en.wikipedia.org/wiki/" + quote(item["title"].replace(" ", "_"), safe=""),
                 "snippet": extract_html(item.get("snippet", ""))[1]}
                for item in data["query"]["search"]
            ]
        data = self._json_request(
            "POST", "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {self.settings.tavily_api_key}"},
            json={"query": query, "search_depth": "basic", "max_results": self.settings.max_results,
                  "include_answer": False, "include_raw_content": False,
                  "include_domains": list(self.settings.allowed_domains)},
        )
        return [{"title": item.get("title", ""), "url": item["url"],
                 "snippet": item.get("content", "")} for item in data["results"]]

    def search_sources(self, query):
        if not isinstance(query, str) or not query.strip() or len(query) > 1000:
            return {"error": "invalid_search_query"}
        query_key = " ".join(query.lower().split())
        if query_key in self.queries:
            return copy.deepcopy(self.queries[query_key])
        try:
            candidates = self._search(query.strip())
            results, seen = [], set()
            blocked = 0
            for candidate in candidates[:self.settings.max_results]:
                try:
                    url = canonical_url(candidate["url"], self.settings.allowed_domains)
                except RetrievalError:
                    blocked += 1
                    continue
                source_id = "web_" + hashlib.sha256(url.encode()).hexdigest()[:24]
                if source_id in seen:
                    continue
                seen.add(source_id)
                if source_id not in self.sources:
                    if len(self.sources) >= self.settings.max_sources:
                        raise RetrievalError("source_registry_limit")
                    self.sources[source_id] = {
                        "source_id": source_id, "url": url,
                        "title": str(candidate["title"])[:500], "discovered_at": utc_now(),
                    }
                results.append({**self.sources[source_id], "snippet": str(candidate.get("snippet", ""))[:800]})
            outcome = {"results": results, "provider": self.settings.provider, "blocked_results": blocked}
            self.queries[query_key] = outcome
            self._save()
            return copy.deepcopy(outcome)
        except RetrievalError as exc:
            return {"error": exc.code}
        except requests.Timeout:
            return {"error": "search_timeout"}
        except requests.RequestException:
            return {"error": "search_request_failed"}
        except (ValueError, TypeError, KeyError, AttributeError):
            return {"error": "invalid_search_response"}

    def _fetch(self, original_url):
        url = original_url
        for attempt in range(4):
            url = canonical_url(url, self.settings.allowed_domains)
            check_public_dns(url)
            with self.session.get(
                url, timeout=(5, self.settings.timeout), allow_redirects=False,
                stream=True, headers={"User-Agent": "ResearchAgentLearningProject/0.1"},
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location:
                        raise RetrievalError("invalid_redirect")
                    url = urljoin(url, location)
                    continue
                if response.status_code == 429:
                    raise RetrievalError("rate_limited")
                response.raise_for_status()
                if response.status_code != 200:
                    raise RetrievalError("page_http_error")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower().strip()
                if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                    raise RetrievalError("unsupported_content_type")
                body = self._body(response)
                encoding = response.encoding or "utf-8"
                decoded = body.decode(encoding, errors="replace")
                title, text = ("", decoded) if content_type == "text/plain" else extract_html(decoded)
                if not text.strip():
                    raise RetrievalError("empty_page_text")
                text = text.strip()
                truncated = len(text) > self.settings.max_text_chars
                text = text[:self.settings.max_text_chars]
                return {
                    "resolved_url": url, "retrieved_at": utc_now(), "title": title,
                    "text": text, "content_type": content_type, "truncated": truncated,
                    "content_hash": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
                    "response_hash": "sha256:" + hashlib.sha256(body).hexdigest(),
                }
        raise RetrievalError("redirect_limit")

    def read_source(self, source_id):
        if source_id not in self.sources:
            return {"error": "source_not_found", "source_id": source_id}
        if source_id in self.cache:
            return dict(self.cache[source_id])
        try:
            fetched = self._fetch(self.sources[source_id]["url"])
            if not fetched["title"]:
                fetched["title"] = self.sources[source_id]["title"]
            result = {**self.sources[source_id], **fetched}
            self.cache[source_id] = result
            self._save()
            return dict(result)
        except RetrievalError as exc:
            return {"error": exc.code, "source_id": source_id}
        except requests.Timeout:
            return {"error": "page_timeout", "source_id": source_id}
        except requests.RequestException:
            return {"error": "page_request_failed", "source_id": source_id}
        except (ValueError, LookupError):
            return {"error": "page_decode_failed", "source_id": source_id}
