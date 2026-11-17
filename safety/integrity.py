"""Hash the trusted parts of the repository so any modification is detected."""
from __future__ import annotations

import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TRUSTED = ["rsi", "safety", "benchmarks"]


def fingerprint() -> str:
    h = hashlib.sha256()
    for top in TRUSTED:
        for p in sorted((REPO / top).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                h.update(str(p.relative_to(REPO)).encode())
                h.update(p.read_bytes())
    return h.hexdigest()


class IntegrityError(RuntimeError):
    pass


def verify(expected: str):
    now = fingerprint()
    if now != expected:
        raise IntegrityError("trusted code changed during the experiment; aborting")
