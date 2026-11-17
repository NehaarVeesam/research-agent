# 03 — MCP integration

[Module index](README.md)

## Purpose

Expose tools behind a standard discovery/invocation boundary so the consuming application need not import their implementation.

## Files

- [app/mcp_server.py](../../app/mcp_server.py): registers tool wrappers with `@server.tool()`.
- [app/search.py](../../app/search.py): actual tool logic.
- [app/mcp_tools.py](../../app/mcp_tools.py): discovery adapter, allowlist, argument parsing, invocation, decoding.
- [checks/check_mcp.py](../../checks/check_mcp.py): discovery and invocation smoke check.

## Roles

| Role | Here |
|---|---|
| Host | Research application managing the model, permissions, and workflow |
| Client | `Client` connection owned by the runner |
| Server | Separately launched `app.mcp_server` process |

The client is not the server. One generic LangGraph tools node can invoke either MCP tool; we did not create a workflow node for each function.

## Connection and invocation

```python
parameters = StdioServerParameters(
    command=sys.executable,
    args=["-m", "app.mcp_server"],
    cwd=str(PROJECT_ROOT),
)
```

Entering `async with Client(parameters)` launches/connects to the subprocess; exiting manages cleanup. The SDK handles protocol lifecycle and JSON-RPC communication over stdin/stdout.

```text
client.list_tools()
    → server descriptions and input schemas
    → allowlist filter
    → Qwen-compatible tool definitions

Qwen tool request
    → parse JSON arguments and check allowlist
    → client.call_tool(name, argument_dictionary)
    → server wrapper → search/read function
    → MCP response → ordinary result dictionary
```

Discovery does not authorize every offered tool. The model proposes arguments; the server SDK applies registered schema validation. Protocol/connection exceptions and returned tool failures are distinct.

## Result representation

Our local tool initially returned JSON text in `content`, with `structured_content=None`. The adapter checks `is_error`, then uses structured content if present or parses the single text block. It expects JSON objects for these project tools; it is not a general multimodal MCP decoder.

## Why MCP rather than an import?

An import is simpler for internal Python logic. MCP is useful when providers are independently maintained or consumed by different compatible applications. It does not improve research reasoning automatically or create a security sandbox.

Local stdio requires no HTTP port. A remotely hosted service can use Streamable HTTP. Shared service deployment, authentication, and independent third-party server integration are not implemented here.

## Run and interview question

```bash
python -m checks.check_mcp
```

**What proves this is real MCP?** A client discovers definitions and invokes tools across a subprocess boundary without importing their implementations into the controller.
