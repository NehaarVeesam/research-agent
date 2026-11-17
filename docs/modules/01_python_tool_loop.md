# 01 — Python environment and tool loop

[Module index](README.md)

This note follows the learning sequence. See the [project README](../../README.md) for the complete current workflow; named live runs below are historical observations.

## Purpose

Understand an agent's execution mechanism before putting it behind a framework. The model proposes a next action; Python decides whether and how to execute it.

## Files

- [app/agent.py](../../app/agent.py): original controller, model HTTP request, limits, and entry point.
- [app/search.py](../../app/search.py): fictional documents and actual search/read implementations.
- [checks/check_agent.py](../../checks/check_agent.py): original-controller integration and budget checks.
- [requirements.txt](../../requirements.txt), [.env.example](../../.env.example): dependencies and configuration template.

## Environment and package execution

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Configure your own `.env` from the template without overwriting an existing configuration. Required names are `QWEN_BASE_URL` and `QWEN_MODEL`; `QWEN_API_KEY` is optional and becomes a bearer header. The exact served model identifier matters.

Use `python -m app.agent` from the project root. `-m` resolves a module through Python's import system, keeping sibling packages discoverable. Executing `python checks/check_agent.py` instead places the script directory first on the search path and can break imports of `app`. `__init__.py` identifies our package folders.

## Execution sequence

1. Accept the question and open the MCP connection in the current original-controller implementation.
2. Discover permitted tool definitions.
3. Initialize system/user messages, counters, and trace.
4. Call `call_model(messages, tools)`.
5. If the model requests tools, append its assistant request, execute the requests, append tool observations, and repeat.
6. Otherwise validate the final report and return an outcome.
7. Stop when a configured limit is reached or a handled failure occurs.

The earliest version dispatched local Python functions directly. That direct dispatcher was replaced by MCP; it is not retained as a separate current executable.

## Messages and model access

```text
system: instructions
user: question
assistant: tool request with ID
 tool: result linked through tool_call_id
assistant: next request or answer
```

The next HTTP request sends accumulated history; the endpoint is not assumed to remember the previous request. Appending a message does not itself invoke the model.

`call_model` sends chat-completion JSON and returns the response message with finish-reason and token-usage metadata. Tool fields are omitted when the tools list is empty. A passed `model_call` is a function reference; in tests it can be replaced with a deterministic function.

## Checks and limitations

```bash
python -m checks.check_agent
```

The model choosing to answer is not proof of complete research. Call limits are application policy, not reasoning quality. The original controller remains a simpler reference and has no task planning loop or task JSON repair.

## Interview question

**Does an agent require an agent framework?** No. A bounded Python decision/action/observation loop is a valid implementation. A framework helps organize state, transitions, and later execution infrastructure.
