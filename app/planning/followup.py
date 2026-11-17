"""One explicit feedback-driven research cycle; no model call for scheduling."""
import copy
import logging
import math

from app.planning.tasks import TrackedTask

logger = logging.getLogger("app.workflow.followup")


def followup_targets(state: dict) -> list[dict]:
    outcome = state.get("result") or {}
    report = outcome.get("report", {})
    verification = outcome.get("claim_verification", {})
    targets = []
    for item in verification.get("assessments", []):
        if item["verdict"] == "supported":
            continue
        finding = report["findings"][item["finding_index"]]
        targets.append({"kind": "claim_support", "finding_index": item["finding_index"],
            "claim": finding["claim"], "reason": item["reason"],
            "criterion": "Find read-source evidence that supports or refutes the disputed part of this claim: "
                         + finding["claim"] + " Reviewer concern: " + item["reason"]})
        break  # Target one weak claim; the cycle is intentionally small.
    for task in state.get("tasks", []):
        if task["status"] != "unresolved" or task["task_id"].startswith("followup_"):
            continue
        assessment = state.get("coverage_assessments", {}).get(task["task_id"], {})
        unmet = next((c for c in assessment.get("criteria", []) if c["verdict"] != "addressed"), None)
        index = unmet["criterion_index"] if unmet else 0
        criterion = task["coverage_criteria"][index]
        targets.append({"kind": "coverage", "task_id": task["task_id"], "criterion_index": index,
            "reason": unmet["rationale"] if unmet else "This task has unresolved coverage.",
            "criterion": "Investigate the missing evidence for: " + criterion})
        break
    return targets


def finished_followup_history(state: dict) -> list[dict]:
    history = copy.deepcopy(state.get("followup_history", []))
    if history and history[-1].get("phase") == "researching":
        entry = history[-1]
        outcome = copy.deepcopy(state.get("result") or {})
        entry.update(phase="finished", after=outcome,
            model_calls_used=state["model_count"] - entry["model_calls_before"],
            tool_calls_used=state["tool_count"] - entry["tool_calls_before"])
        current = outcome.get("report", {}).get("findings", [])
        verdicts = {a["finding_index"]: a["verdict"] for a in
                    outcome.get("claim_verification", {}).get("assessments", [])}
        entry["original_claim_tracking"] = [
            {"claim": target["claim"], "outcome": next(
                (verdicts.get(index, "not_assessed") for index, finding in enumerate(current)
                 if finding["claim"] == target["claim"]),
                 "changed_or_removed" if "report" in outcome else "no_updated_report")}
            for target in entry["targets"] if target["kind"] == "claim_support"]
    return history


def schedule_followup_node(state: dict) -> dict:
    outcome = state.get("result") or {}
    count = state.get("followup_count", 0)
    history = finished_followup_history(state)

    def stop(reason):
        logger.info("Follow-up: %s.", reason)
        return {"followup_history": history,
                "followup_decision": {"action": "stop", "reason": reason, "cycles_used": count}}

    if state.get("max_followup_cycles", 1) not in (0, 1):
        return stop("invalid_cycle_limit")
    if not state.get("verify_claims", False) or state.get("max_followup_cycles", 1) == 0:
        return stop("disabled")
    if count >= state.get("max_followup_cycles", 1):
        return stop("cycle_limit_reached")
    allowed = state.get("status") == "answered" or (
        state.get("status") == "invalid_report"
        and outcome.get("reason") == "claim_support_not_established")
    verification = outcome.get("claim_verification", {})
    if not allowed or verification.get("status") not in {"complete", "not_applicable"}:
        return stop("no_valid_assessed_report")
    targets = followup_targets(state)
    if not targets:
        return stop("no_actionable_gaps")
    # Four research turns, coverage, synthesis, one repair allowance, and verification.
    reserve = 7 + math.ceil((len(outcome["report"]["findings"]) + 3) / 4)
    if state["max_model_calls"] - state["model_count"] < reserve:
        return stop("insufficient_model_budget")
    if state["max_tool_calls"] - state["tool_count"] < 2:
        return stop("insufficient_tool_budget")
    task_id = f"followup_{count + 1:03d}"
    task = TrackedTask(task_id=task_id,
        question=("Perform one targeted follow-up within the original research scope: "
                  + state["question"] + ". Address the supplied disputed claim or missing evidence; "
                  "do not assume the previous claim or reviewer is correct."),
        coverage_criteria=[target["criterion"] for target in targets]).model_dump()
    entry = {"cycle": count + 1, "phase": "researching", "task_id": task_id,
             "targets": targets, "before": copy.deepcopy(outcome),
             "coverage_before": copy.deepcopy(state.get("coverage_assessments", {})),
             "model_calls_before": state["model_count"], "tool_calls_before": state["tool_count"],
             "minimum_model_allowance": reserve}
    logger.info("Starting follow-up cycle %s/1: %s, %s evidence targets.", count + 1, task_id, len(targets))
    return {"bounded_web": True, "tasks": [*state["tasks"], task], "followup_count": count + 1,
            "followup_history": [*state.get("followup_history", []), entry],
            "followup_decision": {"action": "research", "task_id": task_id, "cycles_used": count + 1},
            "active_task_id": None, "latest_reply": None, "status": "running", "result": None}


def route_after_followup(state: dict) -> str:
    return "select" if state.get("followup_decision", {}).get("action") == "research" else "stop"
