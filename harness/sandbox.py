"""Inner sandbox: how an approved command is executed."""
import os
import subprocess

COMMAND_TIMEOUT_S = 60


def execute(command: str, workdir: str):
    """Run in bash with cwd=workdir, a timeout and a minimal environment.
    Returns (returncode, combined stdout+stderr)."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": workdir,
           "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        p = subprocess.run(["bash", "-c", command], cwd=workdir, env=env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=COMMAND_TIMEOUT_S, start_new_session=True)
        return p.returncode, p.stdout.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", errors="replace")
        return 124, out + f"\n[command timed out after {COMMAND_TIMEOUT_S}s]"
