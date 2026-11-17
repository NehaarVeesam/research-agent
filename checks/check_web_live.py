"""Opt-in real web search/read through MCP. Does not call an LLM."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp import Client, StdioServerParameters

from app.mcp_tools import discover_model_tools, execute_mcp_tool
from app.retrieval.settings import RetrievalSettings

ROOT = Path(__file__).resolve().parents[1]


async def main(query):
    load_dotenv(ROOT / ".env")
    settings = RetrievalSettings.from_env("web")
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_server"],
                                       cwd=str(ROOT), env=settings.subprocess_env())
    async with Client(parameters) as client:
        tools = await discover_model_tools(client)
        print("Discovered:", [tool["function"]["name"] for tool in tools])
        result = await execute_mcp_tool(client, "search_sources", json.dumps({"query": query}))
        if "error" in result or not result.get("results"):
            raise RuntimeError(f"Search did not produce readable candidates: {result}")
        source_id = result["results"][0]["source_id"]
        document = await execute_mcp_tool(client, "read_source", json.dumps({"source_id": source_id}))
        if "error" in document:
            raise RuntimeError(f"Page retrieval failed: {document}")
        print(json.dumps({key: value for key, value in document.items() if key != "text"}, indent=2))
        print("Text preview:", document["text"][:300])
        print("Live MCP web retrieval passed; no model called.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="Python programming language")
    asyncio.run(main(parser.parse_args().query))
