import asyncio
import json
import sys
from pathlib import Path

from mcp.types import TextContent
from mcp import Client, StdioServerParameters
from mcp_tools import discover_model_tools, execute_mcp_tool

PROJECT_ROOT = Path(__file__).resolve().parent


async def main():
    server_parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(PROJECT_ROOT / "mcp_server.py")],
    )

    async with Client(server_parameters) as client:
        # Discover tool definitions from the running server.
        discovered = await client.list_tools()

        tool_names = {tool.name for tool in discovered.tools}

        print("Discovered tools:", sorted(tool_names))

        assert {"search_sources", "read_source"} <= tool_names

        for tool in discovered.tools:
            print(f"\nTool: {tool.name}")
            print("Description:", tool.description)
            print(
                "Input schema:",
                json.dumps(tool.input_schema, indent=2),
            )

        # Invoke a tool through MCP, not through a local import.
        result = await client.call_tool(
            "read_source",
            {"source_id": "doc_1"},
        )

        if result.is_error:
            raise RuntimeError(f"MCP tool failed: {result.content}")

        # Print the response representation for this learning exercise.
        print("\nStructured content:", result.structured_content)
        print("Content blocks:", result.content)

        document = result.structured_content

        # If structured data is absent, try the JSON text representation.
        if document is None:
            text_blocks = [
                block.text
                for block in result.content
                if isinstance(block, TextContent)
            ]

            if len(text_blocks) != 1:
                raise RuntimeError(
                    "Expected one JSON text block for this document tool."
                )

            try:
                document = json.loads(text_blocks[0])
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "The tool returned text that is not valid JSON."
                ) from exc

        if not isinstance(document, dict):
            raise RuntimeError("Expected a document dictionary.")
        if "error" in document:
            raise RuntimeError(f"Document lookup failed: {document}")

        assert document["source_id"] == "doc_1"
        assert isinstance(document["text"], str)

        print("\nDocument returned through MCP:")
        print(json.dumps(document, indent=2))

        print("\nMCP discovery and invocation succeeded.")

        model_tools = await discover_model_tools(client)

        print("\nTool definitions for Qwen:")
        print(json.dumps(model_tools, indent=2))

        tool_result = await execute_mcp_tool(
            client,
            "read_source",
            json.dumps({"source_id": "doc_1"}),
        )

        assert tool_result.get("source_id") == "doc_1", tool_result

        print("\nAdapter result:")
        print(json.dumps(tool_result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())