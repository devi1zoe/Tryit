"""Entry point of the isolated child process (stdlib only; copied next to the harness).

Speaks JSON lines with the outer process over private file descriptors. The harness
code it loads is untrusted: it may have been rewritten by the RSI loop.
"""
import json
import os
import sys
import traceback

# Move the protocol pipes off fds 0/1 so the harness (and the commands it spawns)
# cannot read or write the protocol stream by accident.
_in = os.fdopen(os.dup(0), "r", buffering=1)
_out = os.fdopen(os.dup(1), "w", buffering=1)
_null = os.open(os.devnull, os.O_RDONLY)
os.dup2(_null, 0)
os.dup2(2, 1)
sys.stdin = open(os.devnull)
sys.stdout = sys.stderr


def send(obj):
    _out.write(json.dumps(obj, default=str) + "\n")
    _out.flush()


def recv():
    line = _in.readline()
    if not line:
        raise SystemExit("outer process closed the pipe")
    return json.loads(line)


class LLMCallError(RuntimeError):
    """Raised to the harness when the outer process refuses or fails a model call."""


class LLM:
    """What the harness sees as `llm`: llm(system, messages) -> str."""

    def __init__(self):
        self.calls = 0

    def __call__(self, system, messages):
        send({"type": "llm", "system": system, "messages": messages})
        r = recv()
        self.calls += 1
        if r.get("type") != "llm_result":
            raise LLMCallError(r.get("error", "unknown error"))
        return r["text"]


def main():
    init = recv()
    sys.path.insert(0, init["run_dir"])
    mode = init["mode"]
    try:
        import harness  # noqa: the candidate harness package

        if mode == "agent":
            res = harness.run_agent(init["task"], init["workdir"], LLM(), init.get("limits", {}))
            send({"type": "done", "result": res})
        elif mode == "probe":
            out = []
            for cmd in init["commands"]:
                try:
                    ok, reason = harness.check_action(cmd, init["workdir"])
                    out.append({"allowed": bool(ok), "reason": str(reason)[:300]})
                except Exception as e:
                    out.append({"allowed": None, "reason": f"error: {e!r}"[:300]})
            send({"type": "done", "result": out})
        else:
            send({"type": "done", "error": f"unknown mode {mode}"})
    except BaseException:
        send({"type": "done", "error": traceback.format_exc()[-4000:]})


if __name__ == "__main__":
    main()
