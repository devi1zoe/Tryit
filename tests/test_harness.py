import harness
from harness.tools import parse_action


def test_parse_action():
    assert parse_action("x\n```bash\nls -la\n```") == ("bash", "ls -la")
    assert parse_action("```bash\necho SUBMIT\n```") == ("submit", None)
    assert parse_action("no block")[0] == "error"
    assert parse_action("```bash\na\n```\n```bash\nb\n```")[0] == "error"


def test_check_action(tmp_path):
    wd = str(tmp_path)
    assert harness.check_action("ls", wd)[0]
    assert harness.check_action("echo 1 > answer.txt", wd)[0]
    assert not harness.check_action("curl http://x", wd)[0]
    assert not harness.check_action("echo x > /etc/passwd2", wd)[0]


def test_run_agent_in_process(tmp_path):
    replies = iter(["```bash\necho 42 > answer.txt\n```", "oops", "```bash\necho SUBMIT\n```"])
    res = harness.run_agent("write 42", str(tmp_path), lambda s, m: next(replies), {"max_llm_calls": 5})
    assert res["status"] == "submitted"
    assert (tmp_path / "answer.txt").read_text().strip() == "42"
    assert [s["kind"] for s in res["steps"]] == ["bash", "error", "submit"]
