"""Parse the model's reply into an action."""
import re

_BLOCK = re.compile(r"```(?:bash|sh)\s*\n(.*?)```", re.DOTALL)


def parse_action(text: str):
    """Return ("bash", cmd), ("submit", None) or ("error", message)."""
    blocks = [b.strip() for b in _BLOCK.findall(text or "")]
    if not blocks:
        return "error", "no ```bash block found"
    if len(blocks) > 1:
        return "error", f"found {len(blocks)} bash blocks, expected exactly one"
    cmd = blocks[0]
    if cmd == "echo SUBMIT":
        return "submit", None
    if not cmd:
        return "error", "empty command"
    return "bash", cmd
