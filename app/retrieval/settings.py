"""Retrieval configuration shared by the host and its MCP subprocess."""

import os
from dataclasses import dataclass, field


DEFAULT_DOMAINS = "en.wikipedia.org,docs.python.org,modelcontextprotocol.io,docs.langchain.com"
RETRIEVAL_ENV_NAMES = (
    "WEB_SEARCH_PROVIDER", "TAVILY_API_KEY", "WEB_ALLOWED_DOMAINS",
    "WEB_MAX_RESULTS", "WEB_TIMEOUT_SECONDS", "WEB_MAX_BYTES", "WEB_MAX_TEXT_CHARS",
)


@dataclass(frozen=True)
class RetrievalSettings:
    backend: str = "local"
    provider: str = "wikipedia"
    allowed_domains: tuple[str, ...] = tuple(DEFAULT_DOMAINS.split(","))
    max_results: int = 3
    timeout: float = 15
    max_bytes: int = 2_000_000
    max_text_chars: int = 100_000
    max_sources: int = 100
    tavily_api_key: str = field(default="", repr=False)

    @classmethod
    def from_env(cls, backend: str | None = None):
        value = cls(
            backend=backend or os.getenv("RESEARCH_BACKEND", "local"),
            provider=os.getenv("WEB_SEARCH_PROVIDER", "wikipedia"),
            allowed_domains=tuple(
                item.strip().lower().rstrip(".")
                for item in os.getenv("WEB_ALLOWED_DOMAINS", DEFAULT_DOMAINS).split(",")
                if item.strip()
            ),
            max_results=int(os.getenv("WEB_MAX_RESULTS", "3")),
            timeout=float(os.getenv("WEB_TIMEOUT_SECONDS", "15")),
            max_bytes=int(os.getenv("WEB_MAX_BYTES", "2000000")),
            max_text_chars=int(os.getenv("WEB_MAX_TEXT_CHARS", "100000")),
            tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
        )
        if value.backend not in {"local", "web"}:
            raise ValueError("RESEARCH_BACKEND must be local or web.")
        if value.provider not in {"wikipedia", "tavily"}:
            raise ValueError("WEB_SEARCH_PROVIDER must be wikipedia or tavily.")
        if not value.allowed_domains:
            raise ValueError("WEB_ALLOWED_DOMAINS must not be empty.")
        if not 1 <= value.max_results <= 10:
            raise ValueError("WEB_MAX_RESULTS must be between 1 and 10.")
        if not 1 <= value.timeout <= 120:
            raise ValueError("WEB_TIMEOUT_SECONDS must be between 1 and 120.")
        if not 1024 <= value.max_bytes <= 10_000_000:
            raise ValueError("WEB_MAX_BYTES must be between 1024 and 10000000.")
        if not 100 <= value.max_text_chars <= 100_000:
            raise ValueError("WEB_MAX_TEXT_CHARS must be between 100 and 100000.")
        if value.backend == "web" and value.provider == "tavily" and not value.tavily_api_key:
            raise ValueError("TAVILY_API_KEY is required for Tavily web search.")
        return value

    def subprocess_env(self):
        return {
            "RESEARCH_BACKEND": self.backend, "WEB_SEARCH_PROVIDER": self.provider,
            "WEB_ALLOWED_DOMAINS": ",".join(self.allowed_domains),
            "WEB_MAX_RESULTS": str(self.max_results), "WEB_TIMEOUT_SECONDS": str(self.timeout),
            "WEB_MAX_BYTES": str(self.max_bytes), "WEB_MAX_TEXT_CHARS": str(self.max_text_chars),
            **({"TAVILY_API_KEY": self.tavily_api_key} if self.tavily_api_key else {}),
        }

    def context(self):
        if self.backend == "local":
            return (
                "Research environment: PaperParse and VisionPages are fictional libraries. "
                "Only three fixed local documents are available through search_sources and "
                "read_source. There is no web access. Record missing evidence rather than "
                "planning external searches or new experiments."
            )
        scope = (
            "Wikipedia articles only; this is not general web search"
            if self.provider == "wikipedia" else "Tavily web-search results"
        )
        return (
            f"Research environment: external retrieval through {scope}. "
            f"Approved page domains: {', '.join(self.allowed_domains)}. "
            "Use search_sources to discover source IDs, then read_source to retrieve text. "
            "Only public HTTPS HTML/plain-text pages are supported; no PDF, login, "
            "JavaScript rendering, private network, or experiments. Record inaccessible or "
            "missing evidence explicitly. Search snippets are not sufficient citation evidence. "
            "Prefer primary sources when the configured search scope permits them."
        )
