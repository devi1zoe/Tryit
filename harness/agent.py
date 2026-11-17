"""The agent loop: model -> parse -> approve -> execute -> observe."""
from . import approval, context, sandbox, tools


def run_agent(task: str, workdir: str, llm, limits: dict) -> dict:
    max_steps = int(limits.get("max_llm_calls", 30))
    messages = [{"role": "user", "content": context.initial_message(task, workdir)}]
    steps = []
    status = "step_limit"
    for _ in range(max_steps):
        try:
            reply = llm(context.SYSTEM_PROMPT, messages)
        except Exception as e:
            status = f"llm_error: {e}"
            break
        messages.append({"role": "assistant", "content": reply})
        kind, cmd = tools.parse_action(reply)
        step = {"kind": kind, "command": cmd}
        if kind == "submit":
            steps.append(step)
            status = "submitted"
            break
        if kind == "error":
            obs = context.format_format_error(cmd)
        else:
            allowed, reason = approval.check_action(cmd, workdir)
            step["approved"] = allowed
            if not allowed:
                obs = context.format_denied(reason)
            else:
                rc, out = sandbox.execute(cmd, workdir)
                step["returncode"] = rc
                obs = context.format_observation(rc, out)
        steps.append(step)
        messages.append({"role": "user", "content": obs})
    return {"status": status, "n_steps": len(steps), "steps": steps}
