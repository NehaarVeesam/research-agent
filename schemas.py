from pydantic import BaseModel, ConfigDict, Field

class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)

class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str = Field(min_length=1)
    evidence: list[EvidenceReference] = Field(min_length=1)

class ResearchReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    findings: list[Finding]
    evidence_gaps: list[str]