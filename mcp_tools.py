import json

from mcp import Client
from mcp.types import TextContent


# Discovery does not automatically authorize a tool.
ALLOWED_TOOLS = {"search_sources", "read_source"}


async def discover_model_tools(client: Client) -> list[dict]:
    discovered = await client.list_tools()

    model_tools = []

    for tool in discovered.tools:
        if tool.name not in ALLOWED_TOOLS:
            continue

        model_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.input_schema,
            },
        })

    return model_tools


async def execute_mcp_tool(
    client: Client,
    name: str,
    raw_arguments: str,
) -> dict:
    if name not in ALLOWED_TOOLS:
        return {"error": "tool_not_allowed", "tool": name}

    try:
        arguments = json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError):
        return {"error": "invalid_json_arguments"}

    if not isinstance(arguments, dict):
        return {"error": "arguments_must_be_an_object"}

    result = await client.call_tool(name, arguments)

    if result.is_error:
        return {
            "error": "mcp_tool_execution_failed",
            "details": [
                block.text
                for block in result.content
                if isinstance(block, TextContent)
            ],
        }

    document = result.structured_content

    if document is None:
        text_blocks = [
            block.text
            for block in result.content
            if isinstance(block, TextContent)
        ]

        if len(text_blocks) != 1:
            return {"error": "unexpected_tool_content"}

        try:
            document = json.loads(text_blocks[0])
        except json.JSONDecodeError:
            return {"error": "tool_content_is_not_json"}

    if not isinstance(document, dict):
        return {"error": "tool_result_must_be_an_object"}

    return document