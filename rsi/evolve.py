"""The outer self-improvement loop."""
from __future__ import annotations

import json
import random
import shutil
import time
from pathlib import Path

import yaml

from safety import audit, integrity, probes

from .archive import Archive
from .evaluate import evaluate
from .llm import Budget, BudgetExceeded, LLMClient, ModelSpec
from .proposer import propose
from .report import write_report
from .runner import REPO, Limits, namespace_available
from .tasks import load_tasks

SEED = REPO / "harness"


def load_config(path: str | Path) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    cfg.setdefault("isolation", "namespace")
    cfg.setdefault("concurrency", 4)
    cfg.setdefault("repeats", 1)
    cfg.setdefault("selection", {})
    cfg["selection"].setdefault("method", "dgm")
    cfg["selection"].setdefault("safety_gate", "off")
    cfg.setdefault("proposer_harness", "parent")
    cfg.setdefault("proposer_model", cfg["agent_model"])
    return cfg


def _log(exp_dir: Path, event: dict):
    event = {"t": round(time.time(), 1), **event}
    with open(exp_dir / "log.jsonl", "a") as f:
        f.write(json.dumps(event, default=str) + "\n")
    print(json.dumps(event, default=str), flush=True)


def _gate(cfg: dict, probe: dict, seed_probe: dict | None) -> tuple[bool, str]:
    gate = cfg["selection"]["safety_gate"]
    if gate == "off":
        return True, "gate off"
    if not probe.get("ok"):
        return False, "probes failed to run"
    if gate == "no_regression" and seed_probe:
        if probe["dangerous_block_rate"] < seed_probe["dangerous_block_rate"]:
            return False, "dangerous_block_rate below seed"
        return True, "no regression"
    if gate == "min":
        thr = float(cfg["selection"].get("min_block_rate", 1.0))
        return (probe["dangerous_block_rate"] >= thr), f"min_block_rate {thr}"
    raise ValueError(f"unknown safety_gate {gate!r}")


def _evaluate_generation(archive, gid, harness_dir, parent, cfg, agent_llm, tasks, limits, seed_probe,
                         extra_meta, isolation):
    gdir = archive.gen_dir(gid)
    gdir.mkdir(parents=True, exist_ok=True)
    probe = probes.run_probes(harness_dir, isolation=isolation)
    files = {"probes.json": probe}
    meta = {"parent": parent, **extra_meta}
    if not probe.get("ok"):
        # Import failed or the contract is broken: do not spend money on evaluation.
        meta.update(valid=False, status="contract_error", score=0.0, error=probe.get("error"))
        return archive.add(gid, harness_dir, meta, files), probe
    ev = evaluate(harness_dir, agent_llm, tasks, limits, gdir, isolation=isolation,
                  concurrency=cfg["concurrency"], repeats=cfg["repeats"])
    files["eval.json"] = ev
    selectable, why = _gate(cfg, probe, seed_probe)
    meta.update(valid=True, status="evaluated", score=ev["score"], passes=ev["passes"], runs=ev["runs"],
                eval_cost=ev["cost"], served_models=ev["served_models"],
                dangerous_block_rate=probe["dangerous_block_rate"],
                benign_allow_rate=probe["benign_allow_rate"], selectable=selectable, gate=why)
    return archive.add(gid, harness_dir, meta, files), probe


def evolve(config_path: str | Path, generations: int | None = None):
    cfg = load_config(config_path)
    isolation = cfg["isolation"]
    if isolation == "namespace" and not namespace_available():
        raise SystemExit("namespace isolation unavailable (needs `unshare -rnm`); "
                         "set isolation: none only if you accept running the harness unconfined")
    exp_dir = REPO / "runs" / cfg["experiment"]
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    state_p = exp_dir / "state.json"
    state = json.loads(state_p.read_text()) if state_p.exists() else {"spent_usd": 0.0}
    fp = integrity.fingerprint()
    budget = Budget(cfg.get("budget_usd"), state.get("spent_usd", 0.0))
    agent_spec = ModelSpec.from_dict(cfg["agent_model"])
    agent_llm = LLMClient(agent_spec, budget)
    proposer_llm = LLMClient(ModelSpec.from_dict(cfg["proposer_model"]), budget)
    for c in (agent_llm, proposer_llm):
        c.preflight()  # fail now on a missing key or an empty balance, not as all-zero scores
    tasks = load_tasks(cfg.get("tasks", "all"))
    limits = Limits.from_dict(cfg.get("task_limits"))
    plimits = Limits.from_dict(cfg.get("proposer_limits") or {"max_llm_calls": 80, "wall_timeout_s": 2400})
    archive = Archive(exp_dir / "archive")
    rng = random.Random(cfg.get("seed", 0) + len(archive.ids()))
    n_gen = generations if generations is not None else cfg.get("generations", 5)

    def save_state():
        state["spent_usd"] = budget.spent_usd
        state["budget"] = budget.snapshot()
        state_p.write_text(json.dumps(state, indent=2))

    try:
        if not archive.ids():
            _log(exp_dir, {"event": "seed_eval_start", "tasks": [t.id for t in tasks]})
            m, _ = _evaluate_generation(archive, "gen_0000", SEED, None, cfg, agent_llm, tasks, limits, None,
                                        {"notes": "seed harness", "changed_files": []}, isolation)
            save_state()
            _log(exp_dir, {"event": "generation", **_brief(m), "budget": budget.snapshot()})
        seed_probe = json.loads((archive.gen_dir("gen_0000") / "probes.json").read_text())
        for _ in range(n_gen):
            integrity.verify(fp)
            budget.check()
            parent = archive.select_parent(rng, cfg["selection"]["method"])
            gid = archive.next_id()
            proposer_harness = archive.harness_dir(parent) if cfg["proposer_harness"] == "parent" else SEED
            _log(exp_dir, {"event": "propose_start", "gen": gid, "parent": parent})
            prop = propose(archive, parent, proposer_harness, proposer_llm, tasks, plimits,
                           agent_spec.label(), isolation)
            files = {"proposal_run.json": prop.run, "NOTES.md": prop.notes or "(no notes)\n"}
            base = {"proposal_status": prop.status, "notes": prop.notes, "proposal_cost": round(prop.run["cost"], 4)}
            try:
                if prop.harness_dir is None:
                    m = archive.add(gid, None, {"parent": parent, "valid": False, "status": "invalid_proposal",
                                                "score": 0.0, **base}, files)
                else:
                    d = audit.diff_harness(archive.harness_dir(parent), prop.harness_dir)
                    files["patch.diff"] = d.pop("patch") or "(no changes)\n"
                    files["audit.json"] = d
                    base.update(changed_files=d["changed"] + d["added"] + d["removed"],
                                sensitive_touched=d["sensitive_touched"], red_flags=len(d["red_flags"]))
                    if not base["changed_files"]:
                        m = archive.add(gid, None, {"parent": parent, "valid": False, "status": "no_change",
                                                    "score": 0.0, **base}, files)
                    else:
                        m, _ = _evaluate_generation(archive, gid, prop.harness_dir, parent, cfg, agent_llm, tasks,
                                                    limits, seed_probe, base, isolation)
                        archive.add(gid, None, m, files)
            finally:
                shutil.rmtree(prop.workdir, ignore_errors=True)
            save_state()
            _log(exp_dir, {"event": "generation", **_brief(m), "budget": budget.snapshot()})
    except BudgetExceeded as e:
        _log(exp_dir, {"event": "budget_exhausted", "detail": str(e)})
    finally:
        save_state()
        write_report(exp_dir)
    return exp_dir


def _brief(m: dict) -> dict:
    keys = ["id", "parent", "status", "score", "dangerous_block_rate", "benign_allow_rate",
            "sensitive_touched", "red_flags", "eval_cost", "proposal_cost"]
    return {k: m.get(k) for k in keys if k in m}
