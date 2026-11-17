# 02 — Structured reports and provenance

[Module index](README.md)

## Purpose

Make generated findings inspectable by code rather than accepting an arbitrary paragraph with plausible-looking citations.

## Files

- [app/schemas.py](../../app/schemas.py): `EvidenceReference`, `Finding`, `ResearchReport`.
- [app/validation.py](../../app/validation.py): `validate_evidence_references()`.
- [checks/check_validation.py](../../checks/check_validation.py): valid quotes, unread sources, invented quotes, and limitations.

## Data contract

```text
ResearchReport
├── findings[]
│   ├── claim
│   └── evidence[]
│       ├── source_id
│       └── quote
└── evidence_gaps[]
```

Pydantic `BaseModel` provides parsing/validation methods. `ConfigDict(extra="forbid")` rejects undeclared fields. `Field(min_length=1)` adds length constraints: for strings it counts characters; for lists it counts items. A constraint on a list does not automatically constrain each string inside it.

`model_validate_json(text)` parses and validates JSON. `model_dump()` returns ordinary Python data. `model_json_schema()` describes the contract for a prompt. Pydantic can coerce some compatible values unless strict behavior is configured.

## Processing sequence

1. Parse the model's complete answer as JSON and validate its nested structure.
2. Build a lookup of successfully read source text from the run's tool trace.
3. Resolve each evidence reference to a read source.
4. Require a nonblank quote that occurs exactly in that text.
5. Return an explicit rejection or an accepted report.

Search results alone do not count as a successful `read_source` call in this policy. Sources read earlier in the run may be reused.

## What the checks mean

| Layer | Establishes | Does not establish |
|---|---|---|
| Schema | Correct fields, types, and declared constraints | Useful or correct content |
| Source reference | Source was read in this run | Source credibility |
| Quote | Quoted text exists in that source | The passage supports the claim |

A true quote about OCR requirements cannot justify a claim that a library is the most accurate. Exact matching is sensitive to spaces and punctuation. Evidence-gap statements are not currently independently verified.

## Run

```bash
python -m checks.check_validation
```

One case deliberately attaches an unsupported claim to a real quote and passes reference checks. That demonstrates the need for later semantic verification.

## Interview question

**Is a valid citation proof that a claim is grounded?** Not by itself. We must assess whether the actual cited passage supports the claim's wording and scope.
