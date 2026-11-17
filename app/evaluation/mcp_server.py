"""Fixture-only MCP server; labels are never exposed as tools or resources."""
import os
from pathlib import Path
from mcp.server import MCPServer
from app.evaluation.dataset import Case, CorpusTools

case = Case.model_validate_json(Path(os.environ["EVAL_CASE_PATH"]).read_text())
tools = CorpusTools(case)
server = MCPServer("Frozen benchmark sources")
server.tool()(tools.search_sources)
server.tool()(tools.read_source)

if __name__ == "__main__": server.run(transport="stdio")
