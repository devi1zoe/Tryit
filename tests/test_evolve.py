import json

import yaml

from conftest import isolation
from rsi import evolve as evo


def test_end_to_end_with_scripted_models(tmp_path, monkeypatch):
    monkeypatch.setattr(evo, "REPO", tmp_path)  # write runs/ into tmp
    proposer_script = [
        "Look first.\n```bash\nls harness archive && cat archive/summary.md\n```",
        "Raise the observation limit.\n```bash\nsed -i 's/MAX_OBS_CHARS = 8000/MAX_OBS_CHARS = 12000/' harness/context.py\n```",
        "```bash\nprintf 'Raised MAX_OBS_CHARS to 12000.\\n' > NOTES.md\n```",
        "```bash\necho SUBMIT\n```",
    ]
    cfg = {
        "experiment": "scripted", "generations": 2, "budget_usd": 1,
        "agent_model": {"provider": "scripted", "name": "agent",
                        "responses": ["```bash\necho 31337 > answer.txt\n```"]},
        "proposer_model": {"provider": "scripted", "name": "proposer", "responses": proposer_script},
        "tasks": ["needle_config", "fix_stats"], "concurrency": 2, "isolation": isolation(),
        "task_limits": {"max_llm_calls": 5, "wall_timeout_s": 120},
        "proposer_limits": {"max_llm_calls": 10, "wall_timeout_s": 120},
    }
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(cfg))
    exp = evo.evolve(p)
    ids = sorted(d.name for d in (exp / "archive").iterdir())
    assert ids == ["gen_0000", "gen_0001", "gen_0002"]
    seed = json.loads((exp / "archive/gen_0000/meta.json").read_text())
    assert seed["score"] == 0.5  # needle solved, fix_stats not
    g1 = json.loads((exp / "archive/gen_0001/meta.json").read_text())
    assert g1["status"] == "evaluated" and g1["changed_files"] == ["context.py"]
    assert "MAX_OBS_CHARS = 12000" in (exp / "archive/gen_0001/patch.diff").read_text()
    assert "12000" in g1["notes"]
    assert 0 < g1["dangerous_block_rate"] <= 1
    assert (exp / "report.md").read_text().count("gen_000") >= 3


def test_bare_off_safety_gate_is_accepted(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("experiment: x\nagent_model: {provider: scripted, name: s}\nselection: {safety_gate: off}\n")
    assert evo.load_config(p)["selection"]["safety_gate"] == "off"
