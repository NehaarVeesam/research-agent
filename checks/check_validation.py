from pydantic import ValidationError
from app.agent import validate_evidence_references
from app.schemas import ResearchReport
from app.search import read_source

# Simulate a trace in which the agent successfully read doc_1
trace = [
    {
        "tool": "read_source",
        "result": read_source("doc_1"),
    }
]

real_quote = (
    "Scanned PDFs require the optional ScanBridge OCR integration."
)

def make_report(claim: str, source_id: str, quote: str) -> ResearchReport:
    return ResearchReport(
        findings=[
            {
                "claim": claim,
                "evidence": [
                    {
                        "source_id": source_id,
                        "quote": quote,
                    }
                ],
            }
        ],
        evidence_gaps=[],
    )

# Case 1: Valid structure, read source, real quote.
valid_report = make_report(
    claim="PaperParse requires ScanBridge for scanned PDFs.",
    source_id="doc_1",
    quote=real_quote,
)

errors = validate_evidence_references(valid_report, trace)
assert errors == [], errors
print("Case 1: Accepted a real quote from a read source.")

# Case 2: The source exists, but was not read in this trace.
unread_source_report = make_report(
    claim="VisionPages includes built-in OCR.",
    source_id="doc_3",
    quote="VisionPages is a fictional library with built-in OCR",
)
errors = validate_evidence_references(unread_source_report, trace)
assert errors, "Expected the unread source to be rejected."
print("Case 2: Rejected an unread source:", errors)

# Case 3: The source was read, but the quote is invented.
invented_quote_report = make_report(
    claim="PaperParse achieves 99% accuracy.",
    source_id="doc_1",
    quote="PaperParse achieves 99% accuracy.",
)

errors = validate_evidence_references(invented_quote_report, trace)
assert errors, "Expected the invented quote to be rejected."
print("Case 3: Rejected an invented quote:", errors)

# Case 4: Missing evidence violates the Pydantic schema.
try:
    ResearchReport(
        findings=[
            {
                "claim": "PaperParse is accurate.",
                "evidence": [],
            }
        ],
        evidence_gaps=[],
    )
except ValidationError:
    print("Case 4: Pydantic rejected an empty evidence list.")
else:
    raise AssertionError("Expected schema validation to fail.")


# Case 5: Real quote, but it does not support the claim.
unsupported_claim_report = make_report(
    claim="PaperParse is more accurate than VisionPages.",
    source_id="doc_1",
    quote=real_quote,
)

errors = validate_evidence_references(unsupported_claim_report, trace)
assert errors == [], errors
print(
    "Case 5: Passed reference checks, despite an unsupported claim. "
    "Semantic verification is still needed."
)
