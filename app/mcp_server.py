import os
from mcp.server import MCPServer

from app.search import read_source as local_read_source
from app.search import search_sources as local_search_sources
from app.retrieval.settings import RetrievalSettings
from app.retrieval.web import WebSources

settings = RetrievalSettings.from_env()
backend = WebSources(settings, store_path=os.getenv("RESEARCH_SOURCE_STATE")) if settings.backend == "web" else None
server = MCPServer("Research Sources")


@server.tool()
def search_sources(query: str) -> dict:
    """Search the configured collection; return source IDs, titles, and snippets.

    Snippets are discovery aids. Read a source before citing it.
    """
    if backend is not None:
        return backend.search_sources(query)
    return local_search_sources(query=query)


@server.tool()
def read_source(source_id: str) -> dict:
    """Read a discovered source ID and return its text and available provenance."""
    if backend is not None:
        return backend.read_source(source_id)
    return local_read_source(source_id=source_id)


if __name__ == "__main__":
    server.run(transport="stdio")
