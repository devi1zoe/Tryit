"""Outer containment: run a candidate harness in an isolated child process.

Isolation (`namespace` mode, Linux user namespaces via `unshare`):
  * no network at all (new, empty network namespace)
  * the repository, /root and other `hide_paths` are covered by empty tmpfs mounts,
    so the harness cannot read benchmark checkers, the archive or credentials
  * the directory holding the harness code is bind-mounted read-only
  * resource limits (address space, file size, open files) and a wall-clock timeout
Model calls are proxied through the parent, which enforces call and token caps.

This layer is NOT editable by the RSI loop. It is weaker than gVisor/Firecracker; see README.
"""
from __future__ import annotations

import json
import os
import resource
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .llm import BudgetExceeded, LLMClient, LLMError

REPO = Path(__file__).resolve().parent.parent
CHILD_SRC = Path(__file__).resolve().parent / "child.py"
WORK_BASE = Path(os.environ.get("TRYIT_WORK", "/tmp/tryit-work"))


@dataclass
class Limits:
    max_llm_calls: int = 30
    max_total_tokens: int = 1_500_000
    wall_timeout_s: int = 900
    mem_bytes: int = 4 * 1024**3
    fsize_bytes: int = 512 * 1024**2

    @classmethod
    def from_dict(cls, d: dict | None) -> "Limits":
        d = d or {}
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class RunResult:
    result: object = None
    error: str | None = None
    killed: str | None = None
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    wall_s: float = 0.0
    served_models: list = field(default_factory=list)
    transcript: list = field(default_factory=list)  # trusted record of model I/O
    stderr_tail: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def namespace_available() -> bool:
    if not shutil.which("unshare"):
        return False
    try:
        r = subprocess.run(["unshare", "-rnm", "true"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def _isolated_cmd(argv: list[str], ro_dirs: list[Path], isolation: str, hide_paths: list[str]) -> list[str]:
    if isolation == "none":
        return argv
    if isolation != "namespace":
        raise ValueError(f"unknown isolation {isolation!r}")
    lines = ["set -e"]
    for p in [str(REPO), "/root", *hide_paths]:
        lines.append(f"if [ -d {shlex.quote(p)} ]; then mount -t tmpfs -o size=1m none {shlex.quote(p)}; fi")
    for d in ro_dirs:
        q = shlex.quote(str(d))
        lines.append(f"mount --bind {q} {q} && mount -o remount,bind,ro {q}")
    lines.append("exec " + " ".join(shlex.quote(a) for a in argv))
    return ["unshare", "-rnm", "--propagation", "private", "sh", "-c", "\n".join(lines)]


def _preexec(limits: Limits):
    def f():
        resource.setrlimit(resource.RLIMIT_AS, (limits.mem_bytes, limits.mem_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (limits.fsize_bytes, limits.fsize_bytes))
        resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))
    return f


def run_child(harness_dir: Path, mode: str, payload: dict, workdir: Path, llm: LLMClient | None,
              limits: Limits, isolation: str = "namespace", hide_paths: list[str] | None = None) -> RunResult:
    """Copy `harness_dir` into a fresh read-only run dir and execute it in the child."""
    WORK_BASE.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="run_", dir=WORK_BASE))
    shutil.copytree(harness_dir, run_dir / "harness", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(CHILD_SRC, run_dir / "child.py")
    argv = [sys.executable, "-I", "-u", "-B", str(run_dir / "child.py")]
    cmd = _isolated_cmd(argv, [run_dir], isolation, hide_paths or [])
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(workdir), "LANG": "C.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1"}
    stderr_path = run_dir.with_suffix(".stderr")
    res = RunResult()
    t0 = time.time()
    with open(stderr_path, "w") as errf:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errf,
                                cwd=workdir, env=env, text=True, bufsize=1,
                                start_new_session=True, preexec_fn=_preexec(limits))

        def kill(reason):
            if res.killed is None:
                res.killed = reason
            try:
                os.killpg(proc.pid, 9)
            except ProcessLookupError:
                pass

        timer = threading.Timer(limits.wall_timeout_s, kill, args=("wall_timeout",))
        timer.start()
        try:
            proc.stdin.write(json.dumps({"mode": mode, "run_dir": str(run_dir), "workdir": str(workdir),
                                         **payload}) + "\n")
            proc.stdin.flush()
            for line in proc.stdout:
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "done":
                    res.result, res.error = msg.get("result"), msg.get("error")
                    break
                if msg.get("type") != "llm":
                    continue
                reply = _serve_llm(msg, llm, limits, res)
                proc.stdin.write(json.dumps(reply) + "\n")
                proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            res.error = res.error or f"pipe error: {e}"
        finally:
            timer.cancel()
            try:
                proc.wait(timeout=5)  # normal exit after sending "done"
            except subprocess.TimeoutExpired:
                kill("did_not_exit")
                proc.wait()
    res.wall_s = round(time.time() - t0, 2)
    if res.result is None and res.error is None:
        res.error = f"child exited without result (killed={res.killed})"
    try:
        res.stderr_tail = stderr_path.read_text(errors="replace")[-3000:]
    except OSError:
        pass
    shutil.rmtree(run_dir, ignore_errors=True)
    stderr_path.unlink(missing_ok=True)
    return res


def _serve_llm(msg: dict, llm: LLMClient | None, limits: Limits, res: RunResult) -> dict:
    if llm is None:
        return {"type": "llm_error", "error": "no model available in this mode"}
    if res.llm_calls >= limits.max_llm_calls:
        return {"type": "llm_error", "error": f"LLM call limit reached ({limits.max_llm_calls})"}
    if res.input_tokens + res.output_tokens >= limits.max_total_tokens:
        return {"type": "llm_error", "error": "token limit reached"}
    messages = msg.get("messages")
    system = msg.get("system") or ""
    if not isinstance(system, str) or not isinstance(messages, list):
        return {"type": "llm_error", "error": "malformed request"}
    try:
        r = llm.complete(system, messages)
    except (LLMError, BudgetExceeded) as e:
        res.transcript.append({"error": str(e)})
        return {"type": "llm_error", "error": str(e)}
    res.llm_calls += 1
    res.input_tokens += r["input_tokens"]
    res.output_tokens += r["output_tokens"]
    res.cost += r["cost"]
    if r["served_model"] not in res.served_models:
        res.served_models.append(r["served_model"])
    last_user = messages[-1]["content"] if messages else ""
    res.transcript.append({"observation": last_user[-6000:], "reply": r["text"],
                           "n_messages": len(messages), "system_chars": len(system),
                           "served_model": r["served_model"], "stop_reason": r["stop_reason"]})
    return {"type": "llm_result", "text": r["text"]}
