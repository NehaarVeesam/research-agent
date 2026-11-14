from mcp.server import MCPServer

from search import read_source as local_read_source
from search import search_sources as local_search_sources

server = MCPServer("Research Sources")

@server.tool()
def search_sources(query:str) -> dict:
    """Search fictional documents and return source IDs, titles, and snippets."""
    return local_search_sources(query=query)


@server.tool()
def read_source(source_id: str) -> dict:
    """Read the full text of a fictional document using its source ID."""
    return local_read_source(source_id=source_id)


if __name__ == "__main__":
    server.run(transport="stdio")
