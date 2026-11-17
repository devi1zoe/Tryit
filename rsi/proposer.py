"""Proposal step: a coding agent edits a copy of the parent harness.

By default the proposer runs on the parent harness itself (self-referential, as in the
Darwin Gödel Machine): the harness being improved is also the one doing the improving.
It sees the archive history through files (as in Meta-Harness), never the graders.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .archive import Archive
from .llm import LLMClient
from .runner import WORK_BASE, Limits, run_child
from .tasks import Task

PROMPT = (Path(__file__).resolve().parent / "prompts" / "proposer.md").read_text()
MAX_HARNESS_BYTES = 1_000_000
MAX_TRACE_CHARS = 60_000


@dataclass
class Proposal:
    harness_dir: Path | None
    workdir: Path
    notes: str
    run: dict
    status: str  # ok | no_change | invalid | error


def _trim_trace(trace: dict) -> dict:
    t = dict(trace)
    t.pop("harness_result", None)
    s = json.dumps(t, default=str)
    if len(s) > MAX_TRACE_CHARS and t.get("transcript"):
        tr = t["transcript"]
        keep = tr[:6] + [{"note": f"... {len(tr) - 12} steps omitted ..."}] + tr[-6:] if len(tr) > 12 else tr
        t["transcript"] = [{k: (v[:2500] if isinstance(v, str) else v) for k, v in step.items()} for step in keep]
    return t


def build_workspace(archive: Archive, parent_id: str, tasks: list[Task], recent_traces: int = 3) -> Path:
    WORK_BASE.mkdir(parents=True, exist_ok=True)
    wd = Path(tempfile.mkdtemp(prefix="propose_", dir=WORK_BASE))
    shutil.copytree(archive.harness_dir(parent_id), wd / "harness",
                    ignore=shutil.ignore_patterns("__pycache__"))
    av = wd / "archive"
    av.mkdir()
    metas = archive.all_meta()
    lines = ["# Archive", "", "| gen | parent | score | status | changed files | note |", "|---|---|---|---|---|---|"]
    for m in metas:
        note = (m.get("notes") or "").replace("\n", " ")[:160]
        lines.append(f"| {m['id']} | {m.get('parent') or '-'} | {m.get('score', 0):.2f} | {m.get('status')} "
                     f"| {', '.join(m.get('changed_files', [])) or '-'} | {note} |")
    (av / "summary.md").write_text("\n".join(lines) + "\n")
    (av / "tasks.md").write_text("\n\n".join(f"## {t.id}\n{t.instruction}" for t in tasks) + "\n")
    with_traces = {parent_id} | {m["id"] for m in metas[-recent_traces:]}
    for m in metas:
        src, dst = archive.gen_dir(m["id"]), av / m["id"]
        dst.mkdir()
        for f in ("patch.diff", "NOTES.md"):
            if (src / f).exists():
                shutil.copy(src / f, dst / f)
        if (src / "eval.json").exists():
            shutil.copy(src / "eval.json", dst / "eval.json")
        if m["id"] in with_traces and (src / "traces").exists():
            (dst / "traces").mkdir()
            for tp in (src / "traces").glob("*.json"):
                (dst / "traces" / tp.name).write_text(
                    json.dumps(_trim_trace(json.loads(tp.read_text())), indent=1, default=str))
    return wd


def propose(archive: Archive, parent_id: str, proposer_harness: Path, llm: LLMClient, tasks: list[Task],
            limits: Limits, agent_model: str, isolation: str) -> Proposal:
    wd = build_workspace(archive, parent_id, tasks)
    pm = archive.meta(parent_id)
    task_text = PROMPT.format(parent_id=parent_id, parent_score=pm.get("score", 0.0),
                              parent_passes=pm.get("passes", 0), parent_runs=pm.get("runs", 0),
                              agent_model=agent_model)
    r = run_child(proposer_harness, "agent", {"task": task_text,
                                             "limits": {"max_llm_calls": limits.max_llm_calls}},
                  wd, llm, limits, isolation=isolation)
    run = {k: v for k, v in r.to_dict().items()}
    notes = (wd / "NOTES.md").read_text()[:4000] if (wd / "NOTES.md").exists() else ""
    hd = wd / "harness"
    if not (hd / "__init__.py").exists():
        return Proposal(None, wd, notes, run, "invalid")
    size = sum(p.stat().st_size for p in hd.rglob("*") if p.is_file())
    if size > MAX_HARNESS_BYTES:
        return Proposal(None, wd, notes, run, "invalid")
    return Proposal(hd, wd, notes, run, "ok")
