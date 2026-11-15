from app.schemas import ResearchReport

def validate_evidence_references(
    report: ResearchReport,
    trace: list[dict],
) -> list[str]:
    read_sources = {}

    for event in trace:
        if event["tool"] != "read_source":
            continue

        result = event["result"]

        if "error" in result:
            continue

        read_sources[result["source_id"]] = result["text"]
    
    errors = []

    for finding_index, finding in enumerate(report.findings, start=1):
        for reference in finding.evidence:
            source_text = read_sources.get(reference.source_id)

            if source_text is None:
                errors.append(
                    f"Finding {finding_index}: source "
                    f"{reference.source_id!r} was not successfully read."
                )
                continue

            if not reference.quote.strip():
                errors.append(
                    f"Finding {finding_index}: quote contains only whitespace."
                )
            elif reference.quote not in source_text:
                errors.append(
                    f"Finding {finding_index}: quote does not occur "
                    f"in source {reference.source_id!r}."
                )

    return errors