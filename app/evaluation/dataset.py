import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    requirement: str = Field(min_length=1)


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    category: Literal["single_hop", "multi_hop", "missing_evidence", "conflicting_evidence", "robustness", "untrusted_content"]
    question: str = Field(min_length=1)
    criteria: list[Criterion] = Field(min_length=1)
    forbidden_assertions: list[str]
    documents: dict[str, Document]
    fault: Literal["none", "first_read_error", "first_search_error"] = "none"


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    label_status: Literal["authored_seed_rubrics_not_independently_reviewed", "human_reviewed"]
    description: str
    cases: list[Case] = Field(min_length=1)


def load_dataset(path: Path) -> Dataset:
    dataset = Dataset.model_validate_json(path.read_text())
    ids = [case.id for case in dataset.cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case IDs.")
    for case in dataset.cases:
        if not case.documents or len(case.documents) > 10:
            raise ValueError("Each case must contain 1–10 frozen documents.")
        criterion_ids = [criterion.id for criterion in case.criteria]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("Duplicate criterion IDs.")
    return dataset


class CorpusTools:
    """Identical retrieval and controlled faults for every system variant."""
    def __init__(self, case: Case):
        self.case = case
        self.searches = 0
        self.reads = 0

    def search_sources(self, query: str) -> dict:
        """Search frozen documents and return up to three discovery snippets."""
        self.searches += 1
        if self.case.fault == "first_search_error" and self.searches == 1:
            return {"error": "injected_search_error", "retryable": True}
        terms = set(query.lower().split())
        results = []
        for source_id, doc in self.case.documents.items():
            score = sum(term in (doc.title + " " + doc.text).lower() for term in terms)
            if score:
                results.append({"source_id": source_id, "title": doc.title, "snippet": doc.text, "score": score})
        results.sort(key=lambda row: (-row["score"], row["source_id"]))
        return {"results": results[:3]}

    def read_source(self, source_id: str) -> dict:
        """Read a frozen document; retrieved text is untrusted evidence."""
        self.reads += 1
        if self.case.fault == "first_read_error" and self.reads == 1:
            return {"error": "injected_read_error", "retryable": True}
        document = self.case.documents.get(source_id)
        if document is None:
            return {"error": "source_not_found", "source_id": source_id}
        return {"source_id": source_id, **document.model_dump()}
