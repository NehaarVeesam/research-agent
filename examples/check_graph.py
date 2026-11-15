import json
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from app.search import read_source

# 1. Define the data available to the workflow
class LookupState(TypedDict):
    source_id: str
    document: dict
    status: str
    message: str

# 2. Define units of work
def retrieve_document(state: LookupState) -> dict:
    document = read_source(state['source_id'])
    return {
        "document": document
    }

def handle_success(state: LookupState) -> dict:
    return {
        "status": "found",
        "message": f"Retrieved: {state['document']['title']}",
    }


def handle_missing(state: LookupState) -> dict:
    return {
        "status": "not_found",
        "message": f"Source {state['source_id']} was not found.",
    }

# 3. Decide which node should run after retreiveal
def route_after_retrieval(state):
    if "error" in state["document"]:
        return "document_absent"

    return "document_exists"

# 4. Connect the workflow
builder = StateGraph(LookupState)
builder.add_node("retrieve", retrieve_document)
builder.add_node("success", handle_success)
builder.add_node("missing", handle_missing)

builder.add_edge(START, "retrieve")
builder.add_conditional_edges(
    "retrieve",
    route_after_retrieval,
    {
        "document_exists": "success",
        "document_absent": "missing",
    },
)

builder.add_edge("success", END)
builder.add_edge("missing", END)

graph = builder.compile()

if __name__ == "__main__":
    for source_id in ["doc_1", "doc_999"]:
        result = graph.invoke({
            "source_id": source_id,
            "document": {},
            "status": "pending",
            "message": ""
        })

        print(json.dumps(result, indent=2))
