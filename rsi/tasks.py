"""Benchmark tasks. Each task lives in benchmarks/tasks/<id>/ with:

  task.yaml   id, instruction, optional limits
  gen.py      build(dir): writes the starting workspace (deterministic)
  check.py    run with cwd=workspace and argv[1]=nonce; prints "PASS <nonce>" on success

Checkers never enter the agent's view (the child cannot see the repository), and the
nonce means a planted module that exits early cannot fake a pass.
"""
from __future__ import annotations

import secrets
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from .runner import WORK_BASE, _isolated_cmd

TASK_ROOT = Path(__file__).resolve().parent.parent / "benchmarks" / "tasks"


@dataclass
class Task:
    id: str
    instruction: str
    path: Path
    split: str = "train"

    def prepare(self) -> Path:
        WORK_BASE.mkdir(parents=True, exist_ok=True)
        wd = Path(tempfile.mkdtemp(prefix=f"ws_{self.id}_", dir=WORK_BASE))
        r = subprocess.run([sys.executable, "-I", str(self.path / "gen.py")], cwd=wd,
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"setup of {self.id} failed: {r.stderr[-2000:]}")
        return wd

    def grade(self, workdir: Path, isolation: str = "namespace") -> dict:
        nonce = secrets.token_hex(8)
        tmp = Path(tempfile.mkdtemp(prefix=f"chk_{self.id}_", dir=WORK_BASE))
        for f in ("check.py", "gen.py"):
            shutil.copy(self.path / f, tmp / f)
        argv = [sys.executable, "-I", "-B", str(tmp / "check.py"), nonce]
        # Network off and repo hidden; the checker dir stays readable.
        cmd = _isolated_cmd(argv, [tmp], isolation, [])
        try:
            r = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=300,
                               env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"})
            out = (r.stdout + r.stderr)[-3000:]
            passed = r.returncode == 0 and f"PASS {nonce}" in r.stdout
        except subprocess.TimeoutExpired:
            out, passed = "checker timeout", False
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return {"passed": passed, "check_output": out}


def load_tasks(ids: list[str] | str | None = "all", split: str | None = None) -> list[Task]:
    tasks = []
    for d in sorted(TASK_ROOT.iterdir()):
        if not (d / "task.yaml").exists():
            continue
        meta = yaml.safe_load((d / "task.yaml").read_text())
        t = Task(id=meta["id"], instruction=meta["instruction"].strip(), path=d,
                 split=meta.get("split", "train"))
        tasks.append(t)
    if ids not in (None, "all"):
        want = set(ids)
        tasks = [t for t in tasks if t.id in want]
        missing = want - {t.id for t in tasks}
        if missing:
            raise ValueError(f"unknown tasks: {sorted(missing)}")
    if split:
        tasks = [t for t in tasks if t.split == split]
    return tasks
