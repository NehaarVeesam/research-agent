"""Final verification gate: preserve weak findings and fail closed for review."""
import logging
import math

import requests

from app.schemas import ResearchReport
from app.validation import validate_evidence_references
from app.verification.claims import BATCH_SIZE, assess_claim_batch

logger = logging.getLogger("app.workflow.verification")


def make_claim_verification_node(model_call):
    async def verify_node(state):
        if state.get("status") != "answered" or not state.get("verify_claims", True):
            return {}
        outcome = dict(state["result"])
        checks = {**outcome.get("checks", {}), "claim_support": "incomplete"}
        outcome["checks"] = checks
        report = ResearchReport.model_validate(outcome["report"])
        assessments = []
        count = state["model_count"]
        total = math.ceil(len(report.findings) / BATCH_SIZE)
        record = {"method": "qwen_claim_to_citation_assessment", "status": "incomplete",
                  "assessments": assessments, "batches_completed": 0,
                  "batches_total": total, "model_calls": 0}

        def finish(status, reason=None):
            outcome["status"] = status
            if reason:
                outcome["reason"] = reason
            outcome["claim_verification"] = record
            return {"status": status, "result": outcome, "model_count": count}

        errors = validate_evidence_references(report, state["trace"])
        if errors:
            outcome["validation_errors"] = errors
            checks["claim_support"] = "not_checked"
            return finish("invalid_report", "verification_requires_valid_references")
        if not report.findings:
            record["status"] = "not_applicable"
            checks["claim_support"] = "not_applicable"
            logger.info("Claim verification: no findings; report contains gaps only.")
            return finish("answered")

        for start in range(0, len(report.findings), BATCH_SIZE):
            if count >= state["max_model_calls"]:
                logger.warning("Claim verification stopped: model-call budget exhausted.")
                return finish("budget_exhausted", "claim_verification_budget_exhausted")
            indices = list(range(start, min(start + BATCH_SIZE, len(report.findings))))
            count += 1
            record["model_calls"] += 1
            logger.info("Verifying claims %s (model call %s/%s)...", indices, count, state["max_model_calls"])
            try:
                batch = await assess_claim_batch(report, state["trace"], indices, model_call)
            except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
                record["status"] = "failed"
                checks["claim_support"] = "failed"
                outcome["error"] = str(exc)
                logger.warning("Claim verification failed (%s).", type(exc).__name__)
                return finish("failed", "claim_verification_failed")
            assessments.extend(item.model_dump() for item in batch.assessments)
            record["batches_completed"] += 1

        assessments.sort(key=lambda item: item["finding_index"])
        record["status"] = "complete"
        record["counts"] = {verdict: sum(item["verdict"] == verdict for item in assessments)
                            for verdict in ("supported", "partially_supported", "unsupported")}
        supported = all(item["verdict"] == "supported" for item in assessments)
        checks["claim_support"] = "passed" if supported else "needs_review"
        logger.info("Claim verification complete: %s.", record["counts"])
        return finish("answered" if supported else "invalid_report",
                      None if supported else "claim_support_not_established")
    return verify_node
