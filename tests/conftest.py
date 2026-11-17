import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def _work_base(tmp_path, monkeypatch):
    import rsi.runner as runner
    import rsi.tasks as tasks
    import rsi.proposer as proposer
    import safety.probes as probes
    wb = tmp_path / "work"
    for m in (runner, tasks, proposer, probes):
        monkeypatch.setattr(m, "WORK_BASE", wb)
    yield


def isolation():
    from rsi.runner import namespace_available
    return "namespace" if namespace_available() else "none"
