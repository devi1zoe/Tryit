"""Markdown report of an experiment."""
from __future__ import annotations

import json
from pathlib import Path

from .archive import Archive


def _f(x, fmt="{:.2f}"):
    return "-" if x is None else fmt.format(x)


def write_report(exp_dir: Path) -> Path:
    exp_dir = Path(exp_dir)
    archive = Archive(exp_dir / "archive")
    metas = archive.all_meta()
    state = json.loads((exp_dir / "state.json").read_text()) if (exp_dir / "state.json").exists() else {}
    lines = [f"# Experiment `{exp_dir.name}`", "",
             f"Spent: ${state.get('spent_usd', 0):.2f}", "",
             "| gen | parent | status | score | dangerous blocked | benign allowed | safety files touched | red flags | selectable | cost |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for m in metas:
        cost = (m.get("eval_cost") or 0) + (m.get("proposal_cost") or 0)
        lines.append(
            f"| {m['id']} | {m.get('parent') or '-'} | {m.get('status')} | {_f(m.get('score'))} "
            f"| {_f(m.get('dangerous_block_rate'))} | {_f(m.get('benign_allow_rate'))} "
            f"| {', '.join(m.get('sensitive_touched') or []) or '-'} | {m.get('red_flags', '-')} "
            f"| {m.get('selectable', '-')} | ${cost:.2f} |")
    valid = [m for m in metas if m.get("valid")]
    if valid:
        best = max(valid, key=lambda m: m["score"])
        lines += ["", f"Best: **{best['id']}** score {best['score']:.2f}"]
        chain, cur = [], best
        while cur:
            chain.append(cur["id"])
            cur = next((m for m in metas if m["id"] == cur.get("parent")), None)
        lines.append("Lineage: " + " <- ".join(chain))
    lines += ["", "## Per-task results", ""]
    tids = sorted({t for m in valid for t in _per_task(archive, m["id"])})
    if tids:
        lines.append("| gen | " + " | ".join(tids) + " |")
        lines.append("|---|" + "---|" * len(tids))
        for m in valid:
            pt = _per_task(archive, m["id"])
            lines.append(f"| {m['id']} | " + " | ".join(
                f"{pt[t]['passes']}/{pt[t]['runs']}" if t in pt else "-" for t in tids) + " |")
    lines += ["", "## Proposal notes", ""]
    for m in metas[1:]:
        lines.append(f"- **{m['id']}** ({m.get('status')}): {(m.get('notes') or '').strip()[:600]}")
    p = exp_dir / "report.md"
    p.write_text("\n".join(lines) + "\n")
    return p


def _per_task(archive: Archive, gid: str) -> dict:
    p = archive.gen_dir(gid) / "eval.json"
    return json.loads(p.read_text())["per_task"] if p.exists() else {}
