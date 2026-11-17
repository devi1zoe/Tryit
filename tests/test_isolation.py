import shutil
from pathlib import Path

import pytest

from rsi.llm import Budget, LLMClient, ModelSpec
from rsi.runner import REPO, Limits, namespace_available, run_child

pytestmark = pytest.mark.skipif(not namespace_available(), reason="needs unshare")


def _harness(tmp_path: Path, body: str) -> Path:
    h = tmp_path / "h" / "harness"
    h.mkdir(parents=True)
    (h / "__init__.py").write_text(body)
    return h


PROBE_BODY = '''
import os, socket
def check_action(c, w):
    return True, "ok"
def run_agent(task, workdir, llm, limits):
    out = {}
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=2); out["net"] = True
    except OSError:
        out["net"] = False
    out["repo_visible"] = os.path.exists(%r)
    try:
        open(os.path.join(os.path.dirname(__file__), "x"), "w"); out["harness_writable"] = True
    except OSError:
        out["harness_writable"] = False
    open(os.path.join(workdir, "w.txt"), "w").write("ok")
    out["reply"] = llm("sys", [{"role": "user", "content": "hi"}])
    try:
        llm("sys", [{"role": "user", "content": "again"}]); out["second_call"] = True
    except Exception as e:
        out["second_call"] = str(e)
    return out
''' % str(REPO / "rsi")


def test_child_is_contained(tmp_path):
    h = _harness(tmp_path, PROBE_BODY)
    wd = tmp_path / "wd"
    wd.mkdir()
    llm = LLMClient(ModelSpec(provider="scripted", name="s", responses=["pong"]), Budget())
    r = run_child(h, "agent", {"task": "t", "limits": {}}, wd, llm, Limits(max_llm_calls=1))
    assert r.error is None, r.error
    assert r.result["net"] is False
    assert r.result["repo_visible"] is False
    assert r.result["harness_writable"] is False
    assert r.result["reply"] == "pong"
    assert "limit" in r.result["second_call"]
    assert (wd / "w.txt").read_text() == "ok"
    assert r.llm_calls == 1 and r.transcript[0]["reply"] == "pong"


def test_wall_timeout_kills_child(tmp_path):
    h = _harness(tmp_path, "import time\ndef check_action(c,w): return True,''\n"
                           "def run_agent(t,w,l,lim):\n    time.sleep(60)\n")
    wd = tmp_path / "wd"
    wd.mkdir()
    r = run_child(h, "agent", {"task": "t"}, wd, None, Limits(wall_timeout_s=2))
    assert r.killed == "wall_timeout" and r.wall_s < 20
