"""Command line: python -m rsi <command> ..."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .llm import Budget, LLMClient, ModelSpec
from .runner import REPO, Limits


def _agent(path: str):
    cfg = yaml.safe_load(Path(path).read_text())
    harness = Path(cfg.get("harness", "harness"))
    if not harness.is_absolute():
        harness = REPO / harness
    return cfg, ModelSpec.from_dict(cfg["model"]), harness, Limits.from_dict(cfg.get("limits"))


def cmd_run(a):
    from .evaluate import run_task
    from .tasks import load_tasks
    cfg, spec, harness, limits = _agent(a.agent)
    budget = Budget(a.budget)
    task = load_tasks([a.task])[0]
    llm = LLMClient(spec, budget)
    llm.preflight()
    r = run_task(task, harness, llm, limits, a.isolation, keep_workdir=a.keep)
    if a.show:
        for i, s in enumerate(r["transcript"]):
            print(f"\n===== step {i} =====\n--- observation ---\n{s.get('observation', s)[-1500:]}\n--- reply ---\n{s.get('reply', '')}")
    print(json.dumps({k: r[k] for k in ("task", "passed", "harness_status", "llm_calls", "cost", "wall_s", "killed",
                                        "error", "served_models", "workdir")}, indent=2))
    print("check output:", r["check_output"][-800:])


def cmd_eval(a):
    from .evaluate import evaluate
    from .tasks import load_tasks
    from safety.probes import run_probes
    cfg, spec, harness, limits = _agent(a.agent)
    budget = Budget(a.budget)
    tasks = load_tasks(a.tasks.split(",") if a.tasks else "all")
    out = Path(a.out) if a.out else REPO / "runs" / "evals" / cfg.get("name", "agent")
    out.mkdir(parents=True, exist_ok=True)
    llm = LLMClient(spec, budget)
    llm.preflight()
    ev = evaluate(harness, llm, tasks, limits, out, isolation=a.isolation,
                  concurrency=a.concurrency, repeats=a.repeats)
    ev["probes"] = run_probes(harness, isolation=a.isolation)
    (out / "eval.json").write_text(json.dumps(ev, indent=2))
    print(json.dumps({"score": ev["score"], "cost": ev["cost"],
                      "per_task": {k: f"{v['passes']}/{v['runs']}" for k, v in ev["per_task"].items()},
                      "dangerous_block_rate": ev["probes"].get("dangerous_block_rate"),
                      "benign_allow_rate": ev["probes"].get("benign_allow_rate"), "out": str(out)}, indent=2))


def cmd_probe(a):
    from safety.probes import run_probes
    print(json.dumps(run_probes(Path(a.harness).resolve(), isolation=a.isolation), indent=2))


def cmd_evolve(a):
    from .evolve import evolve
    exp = evolve(a.config, a.generations)
    print(f"report: {exp / 'report.md'}")


def cmd_report(a):
    from .report import write_report
    print(write_report(Path(a.exp_dir)).read_text())


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m rsi")
    sub = p.add_subparsers(dest="cmd", required=True)
    iso = dict(default="namespace", choices=["namespace", "none"])

    s = sub.add_parser("run", help="run one agent (model + harness) on one task")
    s.add_argument("--agent", required=True)
    s.add_argument("--task", required=True)
    s.add_argument("--show", action="store_true", help="print the trajectory")
    s.add_argument("--keep", action="store_true", help="keep the workspace")
    s.add_argument("--budget", type=float, default=5.0)
    s.add_argument("--isolation", **iso)
    s.set_defaults(f=cmd_run)

    s = sub.add_parser("eval", help="evaluate an agent on the benchmark")
    s.add_argument("--agent", required=True)
    s.add_argument("--tasks")
    s.add_argument("--out")
    s.add_argument("--concurrency", type=int, default=4)
    s.add_argument("--repeats", type=int, default=1)
    s.add_argument("--budget", type=float, default=20.0)
    s.add_argument("--isolation", **iso)
    s.set_defaults(f=cmd_eval)

    s = sub.add_parser("probe", help="run the safety probes against a harness")
    s.add_argument("--harness", default=str(REPO / "harness"))
    s.add_argument("--isolation", **iso)
    s.set_defaults(f=cmd_probe)

    s = sub.add_parser("evolve", help="run the self-improvement loop")
    s.add_argument("--config", required=True)
    s.add_argument("--generations", type=int)
    s.set_defaults(f=cmd_evolve)

    s = sub.add_parser("report", help="rebuild an experiment report")
    s.add_argument("exp_dir")
    s.set_defaults(f=cmd_report)

    a = p.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main(sys.argv[1:])
