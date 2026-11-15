import asyncio
import json

from app.workflow.runner import run_graph_agent


def fake_model(messages: list[dict], tools: list[dict]) -> dict:
    if messages[-1]["role"] != "tool":
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": "read_1",
                    "type": "function",
                    "function": {
                        "name": "read_source",
                        "arguments": '{"source_id": "doc_1"}',
                    },
                }
            ],
        }

    # Confirm that the MCP observation reached the model.
    document = json.loads(messages[-1]["content"])
    assert document["source_id"] == "doc_1"
    assert messages[-1]["tool_call_id"] == "read_1"

    return {
        "content": json.dumps({
            "findings": [
                {
                    "claim": "Scanned PDFs require ScanBridge.",
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
    }


async def main():
    result = await run_graph_agent(
        "Explain PaperParse scanned PDF support.",
        model_call=fake_model,
    )

    assert result["status"] == "answered", result
    assert result["model_calls"] == 2
    assert result["tool_calls"] == 1
    assert result["checks"]["evidence_references"] == "passed"

    print(json.dumps(result, indent=2))
    print("\nComplete graph check passed.")


if __name__ == "__main__":
    asyncio.run(main())