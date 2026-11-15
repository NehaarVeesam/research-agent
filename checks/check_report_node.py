import json

from langgraph.graph import END, START, StateGraph

from app.search import read_source
from app.workflow.nodes import validate_report_node
from app.workflow.state import ResearchState


def make_state(answer: str) -> ResearchState:
    return {
        "messages": [],
        "trace": [
            {
                "tool": "read_source",
                "result": read_source("doc_1"),
            }
        ],
        "latest_reply": {"content": answer},
        "model_count": 1,
        "tool_count": 1,
        "max_model_calls": 6,
        "max_tool_calls": 8,
        "status": "running",
        "result": None,
    }


if __name__ == "__main__":
    builder = StateGraph(ResearchState)
    builder.add_node("validate", validate_report_node)
    builder.add_edge(START, "validate")
    builder.add_edge("validate", END)
    graph = builder.compile()

    valid_answer = json.dumps({
        "findings": [
            {
                "claim": "PaperParse requires ScanBridge for scanned PDFs.",
                "evidence": [
                    {
                        "source_id": "doc_1",
                        "quote": (
                            "Scanned PDFs require the optional "
                            "ScanBridge OCR integration."
                        ),
                    }
                ],
            }
        ],
        "evidence_gaps": [],
    })

    cases = [
        ("valid report", valid_answer, "answered"),
        ("invalid JSON", "not JSON", "invalid_report"),
        ("empty response", "", "failed"),
    ]

    for label, answer, expected_status in cases:
        final_state = graph.invoke(make_state(answer))

        assert final_state["status"] == expected_status, final_state
        print(f"{label}: {final_state['status']}")

    print("\nReport-node checks passed.")