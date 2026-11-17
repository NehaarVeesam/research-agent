"""Reproducible frozen-source benchmark. Qwen is used for research and blind grading."""
import argparse
import asyncio
import csv
import hashlib
import io
import json
import logging
import math
import os
import platform
import threading
import time
from importlib.metadata import version
from pathlib import Path

from app.agent import API_KEY, BASE_URL, MODEL, call_model
from app.evaluation.dataset import load_dataset
from app.evaluation.grading import grade_report
from app.evaluation.systems import VARIANTS, run_system
from app.workflow.artifacts import RunArtifacts, utc_now
from app.workflow.persistent import code_fingerprint, exclusive_run
from app.workflow.runner import PROJECT_ROOT

logger = logging.getLogger("app.workflow.evaluation")
DEFAULT_DATASET = PROJECT_ROOT / "benchmarks" / "research_v1.json"


def usage_stats(events, stage):
    current = None; requests = {}; responses = {}
    for event in events:
        if event["event"] == "phase": current = event["stage"]
        elif event["event"] == "request": requests[event["call_id"]] = current
        elif event["event"] == "response": responses[event["call_id"]] = event["reply"].get("usage")
    ids = [key for key, value in requests.items() if value == stage]
    known = [responses[key] for key in ids if isinstance(responses.get(key), dict)
             and isinstance(responses[key].get("prompt_tokens"), int)
             and isinstance(responses[key].get("completion_tokens"), int)]
    return {"calls": len(ids), "usage_missing_calls": len(ids) - len(known),
            "prompt_tokens": sum(u["prompt_tokens"] for u in known) if known else None,
            "completion_tokens": sum(u["completion_tokens"] for u in known) if known else None}


def aggregate(rows):
    summaries = {}
    for variant in VARIANTS:
        selected = [r for r in rows if r["variant"] == variant]
        if not selected: continue
        metrics = [r["grading"]["metrics"] for r in selected]
        graded = [m for r,m in zip(selected,metrics) if r["grading"]["status"] == "graded"]
        total_refs = sum(m.get("references_total", 0) for m in metrics)
        total_claims = sum(m.get("findings_count", 0) for m in graded)
        summaries[variant] = {
            "trials": len(selected), "graded_trials": len(graded),
            "report_produced_rate": sum(m.get("report_valid", False) for m in metrics) / len(selected),
            "judge_confirmed_task_success_rate": sum(m.get("judge_task_success") is True for m in metrics) / len(selected),
            "rubric_coverage_on_graded": sum(m["rubric_coverage"] for m in graded) / len(graded) if graded else None,
            "citation_validity": sum(m.get("references_valid", 0) for m in metrics) / total_refs if total_refs else None,
            "judge_supported_claim_fraction_on_graded": sum(m.get("supported_findings_count", 0) for m in graded) / total_claims if total_claims else None,
            "mean_research_seconds": sum(r["research_seconds"] for r in selected) / len(selected),
            "mean_research_model_calls": sum(r["research_usage"]["calls"] for r in selected) / len(selected),
            "mean_tool_calls": sum(r["outcome"].get("tool_calls", 0) for r in selected) / len(selected),
            "research_usage_missing_calls": sum(r["research_usage"]["usage_missing_calls"] for r in selected),
        }
    return summaries


def write_summaries(artifacts, rows):
    summary = {"trials_completed": len(rows), "variants": aggregate(rows),
               "warning": "Qwen-assessed seed-rubric results; not independent human-validated accuracy."}
    artifacts.write_json("summary.json", summary)
    columns = ["case_id", "variant", "repeat", "workflow_status", "grade_status", "report_valid",
               "judge_task_success", "rubric_coverage", "citation_validity", "judge_supported_claim_fraction",
               "forbidden_violations", "research_seconds", "grading_seconds", "research_model_calls",
               "tool_calls", "prompt_tokens", "completion_tokens", "usage_missing_calls", "estimated_research_cost_usd", "artifacts_dir"]
    stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=columns); writer.writeheader()
    for row in rows:
        record = {key: row.get(key) for key in columns}
        record.update({key: row["grading"]["metrics"].get(key) for key in ("report_valid", "judge_task_success", "rubric_coverage", "citation_validity", "judge_supported_claim_fraction", "forbidden_violations")})
        record.update(workflow_status=row["outcome"]["status"], grade_status=row["grading"]["status"],
            research_model_calls=row["research_usage"]["calls"], tool_calls=row["outcome"].get("tool_calls", 0),
            **{key: row["research_usage"][key] for key in ("prompt_tokens", "completion_tokens", "usage_missing_calls")})
        writer.writerow(record)
    (artifacts.directory / "results.csv").write_text(artifacts.redact(stream.getvalue()), encoding="utf-8")
    lines = ["# Evaluation results", "", summary["warning"], "",
             "| Variant | Trials / graded | Confirmed task success | Coverage (graded) | Citation validity | Claim support (graded) | Mean seconds | Mean model / tools |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    def fmt(value): return "n/a" if value is None else f"{value:.3f}"
    for name, stats in summary["variants"].items():
        lines.append(f"| {name} | {stats['trials']} / {stats['graded_trials']} | {fmt(stats['judge_confirmed_task_success_rate'])} | {fmt(stats['rubric_coverage_on_graded'])} | {fmt(stats['citation_validity'])} | {fmt(stats['judge_supported_claim_fraction_on_graded'])} | {fmt(stats['mean_research_seconds'])} | {fmt(stats['mean_research_model_calls'])} / {fmt(stats['mean_tool_calls'])} |")
    lines += ["", "Confirmed task success divides fully graded successes by all attempted trials; grading failures remain visible rather than being silently excluded. Coverage and grounding are also reported on graded outputs, with denominators shown. No-citation/no-claim ratios are n/a, not perfect scores.", "", "Research latency/tokens exclude offline grading. Source fixtures and seed labels are frozen; temperature zero does not guarantee bitwise model determinism. Small smoke runs do not establish general superiority."]
    (artifacts.directory / "summary.md").write_text("\n".join(lines) + "\n")


async def run_benchmark(dataset_path=DEFAULT_DATASET, cases=None, variants=VARIANTS, repeats=1,
        model_limit=30, tool_limit=20, output_dir=PROJECT_ROOT / "runs" / "evaluations", resume_dir=None,
        input_price=None, output_price=None, model_call=call_model):
    if resume_dir:
        directory = Path(resume_dir).resolve(); manifest = json.loads((directory / "manifest.json").read_text())
        provider = "qwen" if model_call is call_model else "test_callable"
        if manifest["code_fingerprint"] != code_fingerprint() or manifest["model"] != MODEL or manifest["endpoint"] != BASE_URL or manifest["model_provider"] != provider:
            raise ValueError("Restore the original code/Qwen configuration before resuming this benchmark.")
        artifacts = RunArtifacts.__new__(RunArtifacts)
        artifacts.directory=directory; artifacts.run_id=manifest["run_id"]
        artifacts.secrets=tuple(v for v in (API_KEY,) if v); artifacts.lock=threading.Lock(); artifacts.model_calls=0
        dataset_path=directory/"dataset.json"
        if hashlib.sha256(dataset_path.read_bytes()).hexdigest()!=manifest["dataset_hash"]:
            raise ValueError("Frozen dataset snapshot changed.")
        cases=manifest["cases"]; variants=manifest["variants"]; repeats=manifest["repeats"]
        model_limit=manifest["model_limit"]; tool_limit=manifest["tool_limit"]
        input_price=manifest["input_price_usd_per_million"]; output_price=manifest["output_price_usd_per_million"]
    else:
        if not 1 <= repeats <= 5 or model_limit < 1 or tool_limit < 0:
            raise ValueError("Invalid repeat count or execution budget.")
        if (input_price is None)!=(output_price is None) or any(v is not None and (not math.isfinite(v) or v < 0) for v in (input_price,output_price)):
            raise ValueError("Supply both nonnegative token prices or neither.")
        dataset=load_dataset(Path(dataset_path))
        ids=[c.id for c in dataset.cases]; cases=list(cases or ids)
        if not cases or len(cases)!=len(set(cases)) or set(cases)-set(ids): raise ValueError("Unknown/duplicated case selection.")
        variants=list(variants)
        if not variants or len(variants)!=len(set(variants)) or set(variants)-set(VARIANTS): raise ValueError("Invalid variants.")
        artifacts=RunArtifacts(Path(output_dir),secrets=(API_KEY,));directory=artifacts.directory.resolve()
        artifacts.write_json("dataset.json",dataset.model_dump())
        manifest={"run_id":artifacts.run_id,"started_at":utc_now(),"model":MODEL,"endpoint":BASE_URL,
            "model_provider":"qwen" if model_call is call_model else "test_callable",
            "code_fingerprint":code_fingerprint(),"dataset_hash":hashlib.sha256((directory/"dataset.json").read_bytes()).hexdigest(),
            "dataset_version":dataset.version,"label_status":dataset.label_status,"cases":cases,"variants":variants,
            "repeats":repeats,"model_limit":model_limit,"tool_limit":tool_limit,
            "input_price_usd_per_million":input_price,"output_price_usd_per_million":output_price,
            "python":platform.python_version(),"packages":{name:version(name) for name in ("langgraph","mcp","pydantic","requests")}}
        artifacts.write_json("manifest.json",manifest)
    dataset=load_dataset(Path(dataset_path) if resume_dir else directory/"dataset.json")
    case_lookup={c.id:c for c in dataset.cases}
    with exclusive_run(directory),artifacts.capture_logs():
        (directory/"rows").mkdir(exist_ok=True)
        rows=[]; total=len(cases)*len(variants)*repeats
        for case_id in cases:
            case=case_lookup[case_id]
            for repeat in range(1,repeats+1):
                for variant in variants:
                    row_path=directory/"rows"/f"{case_id}__{variant}__{repeat}.json"
                    if row_path.exists():
                        rows.append(json.loads(row_path.read_text()));continue
                    logger.info("Evaluation %s/%s: %s / %s / repeat %s",len(rows)+1,total,case_id,variant,repeat)
                    trial=RunArtifacts(directory/"trials"/case_id/variant,secrets=(API_KEY,))
                    trial.write_json("case.json",case.model_dump())
                    trial.write_json("run.json", {"case_id":case_id,"variant":variant,
                        "repeat":repeat,"started_at":utc_now(),"benchmark_run_id":artifacts.run_id})
                    def staged(stage):
                        recorded=trial.record_model(model_call)
                        def invoke(messages,tools):
                            trial.append_event({"event":"phase","stage":stage})
                            return recorded(messages,tools)
                        return invoke
                    start=time.perf_counter()
                    with trial.capture_logs():
                        try:
                            outcome=await run_system(variant,case,trial.directory/"case.json",staged("research"),model_limit,tool_limit)
                        except Exception as exc:
                            outcome={"status":"failed","reason":"execution_error","error":str(exc),"trace":[],"tool_calls":0}
                        research_seconds=time.perf_counter()-start
                        trial.write_json("result.json",outcome)
                        logger.info("Offline grading %s / %s...",case_id,variant)
                        grading_start=time.perf_counter()
                        grade=await grade_report(case,outcome,staged("grading"))
                        grading_seconds=time.perf_counter()-grading_start
                    trial.write_json("grade.json",grade)
                    events=[json.loads(line) for line in (trial.directory/"model_calls.jsonl").read_text().splitlines()]
                    usage=usage_stats(events,"research"); grading_usage=usage_stats(events,"grading")
                    cost=None
                    if input_price is not None and usage["usage_missing_calls"]==0 and usage["prompt_tokens"] is not None:
                        cost=(usage["prompt_tokens"]*input_price+usage["completion_tokens"]*output_price)/1_000_000
                    row={"case_id":case_id,"category":case.category,"variant":variant,"repeat":repeat,
                        "outcome":outcome,"grading":grade,"research_seconds":research_seconds,
                        "grading_seconds":grading_seconds,"research_usage":usage,"grading_usage":grading_usage,
                        "estimated_research_cost_usd":cost,"artifacts_dir":str(trial.directory)}
                    artifacts.write_json(str(row_path.relative_to(directory)),row)
                    rows.append(row);write_summaries(artifacts,rows)
        write_summaries(artifacts,rows)
        artifacts.write_json("completion.json",{"finished_at":utc_now(),"trials_completed":len(rows),"trials_expected":total})
        logger.info("Evaluation saved: %s",directory)
    return {"artifacts_dir":str(directory),"summary":aggregate(rows),"trials_completed":len(rows)}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset",type=Path,default=DEFAULT_DATASET)
    parser.add_argument("--cases",nargs="+")
    parser.add_argument("--variants",nargs="+",choices=VARIANTS,default=list(VARIANTS))
    parser.add_argument("--repeats",type=int,default=1)
    parser.add_argument("--max-model-calls",type=int,default=30)
    parser.add_argument("--max-tool-calls",type=int,default=20)
    parser.add_argument("--output-dir",type=Path,default=PROJECT_ROOT/"runs"/"evaluations")
    parser.add_argument("--resume",type=Path)
    parser.add_argument("--input-price-per-million",type=float)
    parser.add_argument("--output-price-per-million",type=float)
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format="%(asctime)s | %(message)s",datefmt="%H:%M:%S")
    print(json.dumps(asyncio.run(run_benchmark(args.dataset,args.cases,args.variants,args.repeats,
        args.max_model_calls,args.max_tool_calls,args.output_dir,args.resume,
        args.input_price_per_million,args.output_price_per_million)),indent=2))
