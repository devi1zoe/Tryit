"""Execute approved commands, retaining large output without buffering it in RAM."""
import os
import signal
import subprocess
import tempfile

COMMAND_TIMEOUT_S = 60
# Leave room for the log reference and timeout diagnostics in the observation.
MAX_OUTPUT_BYTES = 4000


def _stop_group(process):
    """A shell timeout must stop its descendants, not just the waiting shell."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def execute(command: str, workdir: str):
    """Return (returncode, combined output), with a retrievable log if truncated.

    Bash stops on unhandled command and pipeline failures, including inside
    command substitutions. Handle expected nonzero results explicitly.
    Tested conditions and successful commands that merely consume a failing
    substitution can still mask failures, as with errexit generally.
    Output goes straight to a file rather than an unbounded subprocess.PIPE.
    Logs live outside the workspace so they cannot count as deliverable edits.
    Small outputs are returned verbatim and their temporary files are removed.
    """
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": workdir,
           "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
    fd, log_path = tempfile.mkstemp(prefix="harness-output-", suffix=".log", dir="/tmp")
    keep_log = False
    try:
        with os.fdopen(fd, "w+b") as stream:
            process = subprocess.Popen(
                ["bash", "-e", "-o", "pipefail", "-O", "inherit_errexit",
                 "-c", command], cwd=workdir, env=env,
                stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            timed_out = False
            try:
                returncode = process.wait(timeout=COMMAND_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                _stop_group(process)
                returncode = 124
                timed_out = True
            except BaseException:
                _stop_group(process)
                raise

            size = stream.seek(0, os.SEEK_END)
            stream.seek(0)
            if size > MAX_OUTPUT_BYTES:
                half = MAX_OUTPUT_BYTES // 2
                head = stream.read(half).decode("utf-8", errors="replace")
                stream.seek(-half, os.SEEK_END)
                tail = stream.read(half).decode("utf-8", errors="replace")
                output = (head + f"\n... [{size - MAX_OUTPUT_BYTES} output bytes omitted] ...\n"
                          + tail + f"\n[Full command output ({size} bytes): {log_path}\n"
                          "Inspect it with targeted grep or sed ranges; do not assume "
                          "omitted output was empty.]\n")
                keep_log = True
            else:
                output = stream.read().decode("utf-8", errors="replace")
            if timed_out:
                output += f"\n[command timed out after {COMMAND_TIMEOUT_S}s; process group stopped]"
            return returncode, output
    finally:
        if not keep_log:
            os.unlink(log_path)
