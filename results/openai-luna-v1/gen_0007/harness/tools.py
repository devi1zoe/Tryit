"""Parse a single explicit shell action without executing partial fences."""
import re

# Markdown permits up to three spaces before a fence, and longer closing fences.
_OPEN = re.compile(r"^ {0,3}(`{3,})([^`]*)$")
_CLOSE = re.compile(r"^ {0,3}(`{3,})[ \t]*$")


def parse_action(text: str):
    """Return ("bash", cmd), ("submit", None) or ("error", message).

    Read all code fences, not just shell ones: a bash example inside a wider
    non-shell fence is data, not an action. Inline backticks are also data.
    """
    if not isinstance(text, str):
        return "error", "reply must be text containing one fenced bash block"
    blocks = []
    opening = None
    shell = False
    body = []
    for line in text.splitlines(keepends=True):
        marker = line.rstrip("\r\n")
        if opening is None:
            match = _OPEN.fullmatch(marker)
            if match:
                opening = len(match[1])
                shell = match[2].strip() in {"bash", "sh"}
                body = []
        else:
            closing = _CLOSE.fullmatch(marker)
            if closing and len(closing[1]) >= opening:
                if shell:
                    blocks.append("".join(body).strip())
                opening = None
                shell = False
            else:
                nested = _OPEN.fullmatch(marker)
                if nested and len(nested[1]) >= opening:
                    return "error", ("ambiguous fence inside code block; put delimiters "
                                     "on their own lines or use a longer outer fence")
                body.append(line)
    if opening is not None:
        return "error", "unclosed code fence; send one complete fenced bash block"
    if not blocks:
        return "error", "no " + chr(96) * 3 + "bash block found"
    if len(blocks) > 1:
        return "error", f"found {len(blocks)} bash blocks, expected exactly one"
    cmd = blocks[0]
    if cmd == "echo SUBMIT":
        return "submit", None
    if not cmd:
        return "error", "empty command"
    return "bash", cmd
