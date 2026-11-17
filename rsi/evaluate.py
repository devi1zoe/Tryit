"""Evaluate one (model, harness) pair on a set of tasks."""
from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .llm import LLMClient
from .runner import Limits, run_child
from .tasks import Task


def run_task(task: Task, harness_dir: Path, llm: LLMClient, limits: Limits, isolation: str,
             hide_paths: list[str] | None = None, keep_workdir: bool = False) -> dict:
    wd = task.prepare()
    try:
        r = run_child(harness_dir, "agent",
                      {"task": task.instruction, "limits": {"max_llm_calls": limits.max_llm_calls}},
                      wd, llm, limits, isolation=isolation, hide_paths=hide_paths)
        grade = task.grade(wd, isolation=isolation)
    finally:
        if not keep_workdir:
            shutil.rmtree(wd, ignore_errors=True)
    harness_result = r.result if isinstance(r.result, dict) else {"raw": r.result}
    return {
        "task": task.id,
        "passed": grade["passed"],
        "check_output": grade["check_output"],
        "harness_status": harness_result.get("status"),
        "harness_result": harness_result,
        "workdir": str(wd) if keep_workdir else None,
        **{k: v for k, v in r.to_dict().items() if k != "result"},
    }


def evaluate(harness_dir: Path, llm: LLMClient, tasks: list[Task], limits: Limits, out_dir: Path | None,
             isolation: str = "namespace", concurrency: int = 4, repeats: int = 1,
             hide_paths: list[str] | None = None) -> dict:
    jobs = [(t, i) for t in tasks for i in range(repeats)]
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        results = list(ex.map(lambda ti: run_task(ti[0], harness_dir, llm, limits, isolation, hide_paths), jobs))
    per_task: dict[str, dict] = {}
    for (t, i), r in zip(jobs, results):
        if out_dir is not None:
            p = Path(out_dir) / "traces" / f"{t.id}{'' if repeats == 1 else f'.r{i}'}.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(r, indent=2, default=str))
        e = per_task.setdefault(t.id, {"passes": 0, "runs": 0, "llm_calls": 0, "cost": 0.0,
                                       "statuses": [], "errors": []})
        e["runs"] += 1
        e["passes"] += int(r["passed"])
        e["llm_calls"] += r["llm_calls"]
        e["cost"] = round(e["cost"] + r["cost"], 4)
        e["statuses"].append(r["harness_status"] or r["killed"] or "error")
        if r["error"]:
            e["errors"].append(r["error"][-500:])
    n_runs = len(jobs)
    passes = sum(e["passes"] for e in per_task.values())
    served = sorted({m for r in results for m in r["served_models"]})
    return {
        "score": round(passes / n_runs, 4) if n_runs else 0.0,
        "passes": passes,
        "runs": n_runs,
        "cost": round(sum(r["cost"] for r in results), 4),
        "llm_calls": sum(r["llm_calls"] for r in results),
        "served_models": served,
        "per_task": per_task,
    }
