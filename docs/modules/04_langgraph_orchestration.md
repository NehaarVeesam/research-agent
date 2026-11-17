# 04 — LangGraph orchestration and Python foundations

[Module index](README.md)

## Purpose

Express the controller as shared state, execution nodes, and explicit transitions instead of one growing Python loop. LangGraph orchestrates execution; it does not decide evidence quality for us.

## Files

- [app/workflow/state.py](../../app/workflow/state.py): `ResearchState` and update policies.
- [app/workflow/nodes.py](../../app/workflow/nodes.py): node implementations and factories.
- [app/workflow/routing.py](../../app/workflow/routing.py): routing functions.
- [app/workflow/graph.py](../../app/workflow/graph.py): registers and compiles the graph.
- [app/workflow/runner.py](../../app/workflow/runner.py): dependencies, connection lifetime, initial state, execution, public output.

## General skeleton

```text
Define state → Define nodes/routers → Register nodes → Connect edges
    → Compile → Invoke with initial state → Receive final state
```

A node reads state and returns partial updates. A router reads updated state and returns a route label. With `add_conditional_edges("a", router, mapping)`, node `a` runs first, its updates are applied, then the router selects the mapped destination. `START` and `END` are special markers.

## State rules

`TypedDict` describes dictionary keys/types; it does not validate values at runtime. `NotRequired` allows a key to be absent. `Literal` expresses specific permitted values for type checking.

Messages and trace use `Annotated[list[dict], operator.add]`: return only new entries, because the reducer appends them. Counters, tasks, dictionaries, and latest response use replacement updates. Return the new total for a counter and preserve prior dictionary entries when adding a result.

```python
return {
    "messages": [new_message],
    "model_count": state["model_count"] + 1,
}
```

Returning old history plus a new message on an append field would duplicate history. Reaching `END` does not automatically change the application's status field.

## Closures and dependency injection

```python
def make_multiplier(factor):
    def multiply(number):
        return number * factor
    return multiply

double = make_multiplier(2)  # Returns a configured function.
double(5)                    # Executes it later: 10.
```

Likewise, `make_model_node(model_call, tools)` returns a node retaining access to those dependencies. LangGraph later supplies state. The outer function creates the node; the inner function executes the work. `Callable[[list[dict], list[dict]], dict]` describes the supplied model function's interface. Closures are a Python choice, not a LangGraph requirement.

## Async execution

Calling an `async def` function creates a coroutine. `await` waits for its result while allowing the event loop to service other ready tasks. Sequential awaits are still sequential.

`await asyncio.to_thread(model_call, messages, tools)` runs our blocking HTTP function in a worker thread so MCP communication can continue. `asyncio.run(main())` starts an event loop; `graph.ainvoke(state)` executes the async graph.

## Run and limits

```bash
python -m examples.check_graph
python -m examples.python_closure
python -m checks.check_model_node
python -m checks.check_routing
```

The graph-step recursion limit is separate from model/tool budgets. No checkpointer is configured: using LangGraph has not made state durable. No live connection or credentials are stored in persistent state.

## Interview question

**Is each node an agent?** No. A node is a unit of work; one agent can use nodes for planning, tool execution, validation, and synthesis.
