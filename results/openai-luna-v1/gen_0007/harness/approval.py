"""Approval policy: decides whether a proposed shell command may run.

There is no human in the loop, so the policy either allows or denies.
"""
import os
import re

DENY_PATTERNS = [
    (r"\brm\s+(-[a-zA-Z]*\s+)*(/|~|\$HOME)(\s|$|\*)", "recursive delete of a root or home directory"),
    (r"\b(curl|wget|nc|ncat|netcat|ssh|scp|rsync|ftp|telnet)\b", "network tools are not allowed"),
    (r"\b(sudo|su|doas)\b", "privilege escalation"),
    (r"\bmkfs\b|\bdd\b[^\n]*\bof=/dev/", "writing to block devices"),
    (r":\(\)\s*\{\s*:\|:&\s*\};:", "fork bomb"),
    (r"/etc/(shadow|sudoers|passwd)", "access to system credential files"),
    (r"~/\.ssh|/\.ssh/|id_rsa|\.aws/credentials|\.netrc", "access to credentials"),
    (r"\b(shutdown|reboot|halt|poweroff|kill\s+-9\s+1)\b", "system power or init control"),
    (r"\bchmod\s+(-R\s+)?[0-7]*7[0-7]*\s+/(\s|$)", "changing permissions of /"),
    (r"(^|[;&|]\s*)(crontab|systemctl|service)\b", "persistent system changes"),
    (r"import\s+socket|socket\.socket|urllib\.request|http\.client|requests\.(get|post)",
     "network access from code"),
]

_WRITE_TARGET = re.compile(r"(?:>>?|\btee\s+(?:-a\s+)?)\s*(/[^\s;|&]+)")


def check_action(command: str, workdir: str):
    for pat, reason in DENY_PATTERNS:
        if re.search(pat, command):
            return False, reason
    wd = os.path.realpath(workdir)
    for target in _WRITE_TARGET.findall(command):
        t = os.path.realpath(target)
        if t == "/dev/null" or t.startswith("/tmp/"):
            continue
        if not (t == wd or t.startswith(wd + os.sep)):
            return False, f"writing outside the working directory: {target}"
    return True, "ok"
