"""Offline regression tests for action boundaries and execution evidence."""
import json
from pathlib import Path
import tempfile
import unittest

from . import run_agent
from .sandbox import execute
from .tools import parse_action

FENCE = "`" * 3


def action(command, fence=FENCE, language="bash"):
    return "I will run this.\n" + fence + language + "\n" + command + "\n" + fence


class ActionBoundaryTests(unittest.TestCase):
    def test_inline_backticks_are_preserved_in_script(self):
        command = "printf '%s' '" + FENCE + "bash is literal data'"
        self.assertEqual(parse_action(action(command)), ("bash", command))

    def test_inline_fence_is_not_an_action(self):
        self.assertEqual(parse_action("Example: " + FENCE + "bash\ntrue\n" + FENCE)[0],
                         "error")

    def test_wider_fence_can_write_markdown(self):
        command = "cat > README.md <<'EOF'\n" + FENCE + "bash\ntrue\n" + FENCE + "\nEOF"
        reply = action(command, fence="`" * 4)
        self.assertEqual(parse_action(reply), ("bash", command))
        with tempfile.TemporaryDirectory() as wd:
            rc, output = execute(parse_action(reply)[1], wd)
            self.assertEqual(rc, 0, output)
            self.assertEqual(Path(wd, "README.md").read_text(),
                             FENCE + "bash\ntrue\n" + FENCE + "\n")

    def test_bash_example_inside_non_shell_fence_is_not_action(self):
        reply = action(action("touch should_not_exist"), fence="`" * 4, language="text")
        self.assertEqual(parse_action(reply)[0], "error")

    def test_unknown_fence_before_real_action_is_skipped(self):
        reply = action("some text", language="text") + "\n" + action("true")
        self.assertEqual(parse_action(reply), ("bash", "true"))

    def test_reject_incomplete_ambiguous_and_empty_actions(self):
        replies = (
            action("true") + "\n" + action("false"),
            FENCE + "bash\ntrue",
            action("true", fence="`" * 4)[:-4] + FENCE,
            action(""),
            action("true") + "\n" + FENCE + "text\nunfinished",
            "No command was provided.",
            None,
        )
        for reply in replies:
            with self.subTest(reply=reply):
                self.assertEqual(parse_action(reply)[0], "error")

    def test_delimiter_must_occupy_whole_line(self):
        command = "printf ok\n" + FENCE + " not a closing fence\nprintf end"
        self.assertEqual(parse_action(action(command))[0], "error")
        # Explicitly use a wider fence when fence-like lines are script data.
        self.assertEqual(parse_action(action(command, fence="`" * 4)), ("bash", command))

    def test_concatenated_replies_are_ambiguous_not_one_command(self):
        self.assertEqual(parse_action(action("true") + action("false"))[0], "error")

    def test_longer_closer_indentation_and_shell_alias(self):
        reply = "  " + FENCE + "sh\nprintf ok\n " + "`" * 5 + " \t\n"
        self.assertEqual(parse_action(reply), ("bash", "printf ok"))
        self.assertEqual(parse_action(action("echo SUBMIT", fence="`" * 5)),
                         ("submit", None))

    def test_crlf_and_no_final_newline(self):
        self.assertEqual(parse_action(action("true").replace("\n", "\r\n")),
                         ("bash", "true"))


class FailureEvidenceTests(unittest.TestCase):
    def test_failed_command_stops_before_success_or_later_edit(self):
        with tempfile.TemporaryDirectory() as wd:
            rc, output = execute("false\nprintf masked\nprintf bad > late.txt", wd)
            self.assertNotEqual(rc, 0)
            self.assertNotIn("masked", output)
            self.assertFalse(Path(wd, "late.txt").exists())

    def test_failed_pipeline_stops_before_success(self):
        with tempfile.TemporaryDirectory() as wd:
            rc, output = execute("printf x | grep absent | cat\nprintf masked", wd)
            self.assertNotEqual(rc, 0)
            self.assertNotIn("masked", output)

    def test_assertion_failure_is_not_hidden_by_compile(self):
        with tempfile.TemporaryDirectory() as wd:
            Path(wd, "result.py").write_text("value = 1\n")
            rc, output = execute(
                "python3 - <<'CHECK'\nassert False, 'broken check'\nCHECK\n"
                "python3 -m py_compile result.py", wd)
            self.assertNotEqual(rc, 0)
            self.assertIn("AssertionError: broken check", output)

    def test_command_substitution_failure_in_assignment_is_not_masked(self):
        with tempfile.TemporaryDirectory() as wd:
            rc, output = execute("result=$(false)\nprintf masked", wd)
            self.assertNotEqual(rc, 0)
            self.assertNotIn("masked", output)

    def test_substitution_stops_before_a_later_success(self):
        commands = (
            "value=$(false; printf masked)",
            "value=$(printf x | grep absent | cat; printf masked)",
            "outer=$(inner=$(false; printf masked); printf '%s' \"$inner\")",
        )
        for command in commands:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as wd:
                rc, output = execute(
                    command + "\nprintf masked\nprintf bad > late.txt", wd)
                self.assertNotEqual(rc, 0)
                self.assertNotIn("masked", output)
                self.assertFalse(Path(wd, "late.txt").exists())

    def test_successful_and_handled_substitutions_still_work(self):
        commands = (
            ("value=$(printf 'ok\\n\\n')", "ok"),
            ("value=$(false || printf handled)", "handled"),
            ("value=$(if false; then printf bad; else printf fallback; fi)", "fallback"),
            ("if value=$(false); then exit 9; else value=expected; fi", "expected"),
        )
        for command, expected in commands:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as wd:
                rc, output = execute(command + "\nprintf '%s' \"$value\"", wd)
                self.assertEqual((rc, output), (0, expected))

    def test_agent_rejects_failure_hidden_inside_substitution(self):
        commands = iter([
            "printf 'value = 1\\n' > result.py",
            "value=$(python3 -c \"assert False, 'broken check'\"; printf masked)"
            "\nprintf '%s' \"$value\"",
            "echo SUBMIT",
            "value=$(python3 -c 'import result; assert result.value == 1; print(1)')"
            "\ntest \"$value\" = 1",
            "echo SUBMIT",
        ])
        observations = []

        def llm(system, messages):
            observations.append(messages[-1]["content"])
            return action(next(commands))

        with tempfile.TemporaryDirectory() as wd:
            result = run_agent("Create and verify result.py.", wd, llm,
                               {"max_llm_calls": 5})
            self.assertEqual(Path(wd, "result.py").read_text(), "value = 1\n")
        self.assertEqual(result["status"], "submitted")
        self.assertNotEqual(result["steps"][1]["returncode"], 0)
        self.assertFalse(result["steps"][2]["accepted"])
        self.assertIn("last executed command did not succeed", observations[3])
        self.assertIn("AssertionError: broken check", observations[2])
        self.assertNotIn("masked", observations[2])

    def test_expected_failures_can_be_handled(self):
        with tempfile.TemporaryDirectory() as wd:
            rc, output = execute(
                "if false; then exit 7; fi\n"
                "! false\n"
                "false || printf 'handled\\n'\n"
                "if printf x | grep absent; then exit 8; fi\n"
                "printf '%s' \"${MISSING_TEST_VARIABLE:-ok}\"", wd)
            self.assertEqual((rc, output), (0, "handled\nok"))

    def test_shell_state_does_not_persist(self):
        with tempfile.TemporaryDirectory() as wd:
            Path(wd, "child").mkdir()
            self.assertEqual(execute("cd child\nexport AGENT_TEST_VAR=x", wd)[0], 0)
            rc, output = execute("pwd\nprintf '%s' \"${AGENT_TEST_VAR:-fresh}\"", wd)
            self.assertEqual(rc, 0, output)
            self.assertEqual(output, wd + "\nfresh")

    def test_agent_rejects_masked_verification_and_recovers(self):
        commands = iter([
            "printf 'value = 1\\n' > result.py",
            "python3 - <<'CHECK'\nassert False, 'broken check'\nCHECK\n"
            "python3 -m py_compile result.py",
            "echo SUBMIT",
            "python3 -c 'import result; assert result.value == 1'",
            "echo SUBMIT",
        ])
        observations = []

        def llm(system, messages):
            observations.append(messages[-1]["content"])
            return action(next(commands))

        with tempfile.TemporaryDirectory() as wd:
            result = run_agent("Create and verify result.py.", wd, llm,
                               {"max_llm_calls": 5})
        json.dumps(result)
        self.assertEqual(result["status"], "submitted")
        self.assertNotEqual(result["steps"][1]["returncode"], 0)
        self.assertFalse(result["steps"][2]["accepted"])
        self.assertIn("last executed command did not succeed", observations[3])

    def test_agent_rejects_partial_action_without_editing(self):
        replies = iter([
            FENCE + "bash\nprintf unsafe > unwanted.txt",
            action("printf safe > result.txt"),
            action("test \"$(cat result.txt)\" = safe"),
            action("echo SUBMIT"),
        ])
        with tempfile.TemporaryDirectory() as wd:
            result = run_agent("Create and verify result.txt.", wd, lambda *_: next(replies),
                               {"max_llm_calls": 4})
            self.assertFalse(Path(wd, "unwanted.txt").exists())
            self.assertEqual(Path(wd, "result.txt").read_text(), "safe")
        self.assertEqual(result["steps"][0]["kind"], "error")
        self.assertEqual(result["status"], "submitted")


if __name__ == "__main__":
    unittest.main()
