"""Offline checks: python3 -m unittest harness.test_harness."""
import json
import os
import re
import time
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import check_action, run_agent
from .completion import CompletionTracker
from .context import format_observation
from .tools import parse_action
from . import sandbox

FENCE = "`" * 3


def action(command):
    return "I will execute this command.\n" + FENCE + "bash\n" + command + "\n" + FENCE


class HarnessTests(unittest.TestCase):
    def run_script(self, wd, commands):
        observations = []
        replies = iter(action(command) for command in commands)

        def llm(system, messages):
            observations.append(messages[-1]["content"])
            return next(replies)

        result = run_agent("Complete the requested workspace task.", wd, llm,
                           {"max_llm_calls": len(commands)})
        json.dumps(result)
        return result, observations

    def test_premature_submit_then_recover(self):
        with tempfile.TemporaryDirectory() as wd:
            result, obs = self.run_script(wd, [
                "echo SUBMIT", "ls -la", "echo SUBMIT",
                "printf done > result.txt", "test -s result.txt", "echo SUBMIT",
            ])
            self.assertEqual(result["status"], "submitted")
            self.assertFalse(result["steps"][0]["accepted"])
            self.assertFalse(result["steps"][2]["accepted"])
            self.assertIn("No shell commands have been executed", obs[1])
            self.assertIn("No task files have changed", obs[3])
            self.assertEqual(Path(wd, "result.txt").read_text(), "done")

    def test_claimed_success_does_not_count(self):
        with tempfile.TemporaryDirectory() as wd:
            replies = iter(["All tests passed.\n" + action("echo SUBMIT")] * 2)
            result = run_agent("Write a file.", wd, lambda *_: next(replies),
                               {"max_llm_calls": 2})
            self.assertEqual(result["status"], "step_limit")
            self.assertTrue(all(s.get("accepted") is False for s in result["steps"]))

    def test_edit_needs_subsequent_check(self):
        with tempfile.TemporaryDirectory() as wd:
            result, obs = self.run_script(wd, [
                "printf hello > output.txt", "echo SUBMIT",
                "test -s output.txt", "echo SUBMIT",
            ])
            self.assertEqual(result["status"], "submitted")
            self.assertIn("Created: 'output.txt'", obs[2])
            self.assertIn("no successful verification", obs[2])

    def test_normal_edit_and_check_has_no_extra_turn(self):
        with tempfile.TemporaryDirectory() as wd:
            result, _ = self.run_script(wd, [
                "printf x > output.txt", "test -s output.txt", "echo SUBMIT",
            ])
            self.assertEqual(result["status"], "submitted")
            self.assertEqual(result["n_steps"], 3)

    def test_failed_check_blocks_completion(self):
        with tempfile.TemporaryDirectory() as wd:
            result, obs = self.run_script(wd, [
                "printf x > output.txt", "false", "echo SUBMIT",
                "test -s output.txt", "echo SUBMIT",
            ])
            self.assertEqual(result["status"], "submitted")
            self.assertIn("last executed command did not succeed", obs[3])

    def test_read_only_task_can_complete_after_review(self):
        with tempfile.TemporaryDirectory() as wd:
            Path(wd, "existing.txt").write_text("already correct\n")
            result, _ = self.run_script(wd, [
                "cat existing.txt", "echo SUBMIT",
                "grep -qx 'already correct' existing.txt && echo NO_CHANGES_NEEDED", "echo SUBMIT",
            ])
            self.assertEqual(result["status"], "submitted")

    def test_another_edit_invalidates_previous_verification(self):
        with tempfile.TemporaryDirectory() as wd:
            result, _ = self.run_script(wd, [
                "printf x > output.txt", "test -s output.txt",
                "printf y > output.txt", "echo SUBMIT",
            ])
            self.assertEqual(result["status"], "step_limit")
            self.assertFalse(result["steps"][-1]["accepted"])

    def test_snapshot_tracks_content_and_ignores_cache(self):
        with tempfile.TemporaryDirectory() as wd:
            path = Path(wd, "file.txt")
            path.write_text("before")
            tracker = CompletionTracker(wd)
            Path(wd, "__pycache__").mkdir()
            Path(wd, "__pycache__", "junk.pyc").write_bytes(b"cache")
            tracker.observe(0)
            self.assertIn("No task files have changed", tracker.changes())
            path.write_text("after!")
            tracker.observe(0)
            self.assertIn("Modified: 'file.txt'", tracker.changes())
            self.assertIsNotNone(tracker.submission_feedback())
            tracker.observe(0)
            self.assertIsNone(tracker.submission_feedback())
            path.unlink()
            tracker.observe(0)
            self.assertIn("Deleted: 'file.txt'", tracker.changes())
            self.assertIsNotNone(tracker.submission_feedback())

    def test_formatting_and_policy_contract(self):
        self.assertEqual(parse_action(action("echo SUBMIT")), ("submit", None))
        self.assertEqual(parse_action(action("echo ok")), ("bash", "echo ok"))
        self.assertEqual(parse_action("No command")[0], "error")
        self.assertEqual(parse_action(action("true") + action("false"))[0], "error")
        self.assertIn("targeted command", format_observation(0, "x" * 10000))
        with tempfile.TemporaryDirectory() as wd:
            for command in ("ls -la", "python3 -m unittest", "printf x > local.txt"):
                self.assertTrue(check_action(command, wd)[0], command)
            for command in ("r" + "m -rf /", "s" + "udo true",
                            "cat /etc/" + "shadow", "cu" + "rl https://example.invalid",
                            "echo x > " + "/etc/example"):
                self.assertFalse(check_action(command, wd)[0], command)

    def test_denied_command_does_not_count(self):
        with tempfile.TemporaryDirectory() as wd:
            result, _ = self.run_script(wd, ["s" + "udo true", "echo SUBMIT"])
            self.assertEqual(result["status"], "step_limit")
            self.assertFalse(result["steps"][0]["approved"])
            self.assertFalse(result["steps"][1]["accepted"])

    def test_llm_exception_and_empty_budget(self):
        with tempfile.TemporaryDirectory() as wd:
            def failed_llm(*_):
                raise RuntimeError("call budget exhausted")
            result = run_agent("task", wd, failed_llm, {"max_llm_calls": 1})
            self.assertTrue(result["status"].startswith("llm_error:"))
            result = run_agent("task", wd, failed_llm, {"max_llm_calls": 0})
            self.assertEqual(result["status"], "step_limit")


class SandboxTests(unittest.TestCase):
    def test_small_output_stderr_and_exit_code(self):
        with tempfile.TemporaryDirectory() as wd:
            rc, output = sandbox.execute("printf 'out\\n'; printf 'err\\n' >&2; exit 7", wd)
            self.assertEqual(rc, 7)
            self.assertEqual(output, "out\nerr\n")
            self.assertEqual(list(Path(wd).iterdir()), [])

    def test_large_output_is_retrievable_and_not_a_workspace_edit(self):
        with tempfile.TemporaryDirectory() as wd:
            tracker = CompletionTracker(wd)
            rc, output = sandbox.execute(
                "python3 - <<'PY'\n"
                "print('HEAD')\nprint('a' * 6000)\nprint('MIDDLE_NEEDLE')\n"
                "print('z' * 6000)\nprint('TAIL')\nPY", wd)
            self.assertEqual(rc, 0)
            self.assertLess(len(output), 5000)
            self.assertIn("HEAD", output)
            self.assertIn("TAIL", output)
            self.assertNotIn("MIDDLE_NEEDLE", output)
            log = re.search(r"Full command output \(\d+ bytes\): (.+)\n", output).group(1)
            try:
                formatted = format_observation(rc, output)
                self.assertIn(log, formatted)
                self.assertEqual(os.stat(log).st_mode & 0o777, 0o600)
                self.assertIn("MIDDLE_NEEDLE", Path(log).read_text())
                allowed, _ = check_action("grep -n MIDDLE_NEEDLE " + log, wd)
                self.assertTrue(allowed)
                rc, retrieved = sandbox.execute("grep -n MIDDLE_NEEDLE " + log, wd)
                self.assertEqual((rc, retrieved), (0, "3:MIDDLE_NEEDLE\n"))
                tracker.observe(rc, retrieved)
                self.assertEqual(tracker.current, tracker.initial)
                self.assertIsNotNone(tracker.submission_feedback())
            finally:
                Path(log).unlink()


    def test_agent_can_use_saved_output_to_complete_a_task(self):
        with tempfile.TemporaryDirectory() as wd:
            saved_logs = []
            calls = 0

            def llm(system, messages):
                nonlocal calls
                calls += 1
                if calls == 1:
                    return action(
                        "python3 - <<'PY'\n"
                        "print('a' * 6000)\nprint('value=42')\nprint('z' * 6000)\nPY")
                if calls == 2:
                    observation = messages[-1]["content"]
                    self.assertNotIn("value=42", observation)
                    log = re.search(
                        r"Full command output \(\d+ bytes\): (.+)\n", observation).group(1)
                    saved_logs.append(log)
                    return action("grep '^value=' " + log + " > result.txt")
                if calls == 3:
                    return action("test \"$(cat result.txt)\" = 'value=42'")
                return action("echo SUBMIT")

            try:
                result = run_agent("Extract the value line into result.txt.", wd, llm,
                                   {"max_llm_calls": 4})
                self.assertEqual(result["status"], "submitted")
                self.assertEqual(calls, 4)
                self.assertEqual(Path(wd, "result.txt").read_text(), "value=42\n")
                json.dumps(result)
            finally:
                for path in saved_logs:
                    Path(path).unlink()

    def test_large_multibyte_output_keeps_log_reference_in_observation(self):
        with tempfile.TemporaryDirectory() as wd:
            rc, output = sandbox.execute(
                "python3 -c \"print('界' * 6000)\"", wd)
            log = re.search(r"Full command output \(\d+ bytes\): (.+)\n", output).group(1)
            try:
                self.assertEqual(rc, 0)
                self.assertIn(log, format_observation(rc, output))
                self.assertEqual(Path(log).read_text(), "界" * 6000 + "\n")
            finally:
                Path(log).unlink()

    def test_unicode_and_invalid_bytes(self):
        with tempfile.TemporaryDirectory() as wd:
            rc, output = sandbox.execute(
                "python3 -c \"import os; os.write(1, 'café'.encode() + bytes([255]))\"", wd)
            self.assertEqual(rc, 0)
            self.assertEqual(output, "café\ufffd")

    def test_timeout_stops_descendant_and_preserves_partial_output(self):
        with tempfile.TemporaryDirectory() as wd:
            command = (
                "python3 -u -c \"import time; print('started', flush=True); "
                "time.sleep(0.4); open('late.txt', 'w').write('orphan')\" & wait"
            )
            with patch.object(sandbox, "COMMAND_TIMEOUT_S", 0.15):
                rc, output = sandbox.execute(command, wd)
            self.assertEqual(rc, 124)
            self.assertIn("started", output)
            self.assertIn("process group stopped", output)
            time.sleep(0.5)
            self.assertFalse(Path(wd, "late.txt").exists())

    def test_temporary_small_output_logs_are_cleaned_up(self):
        with tempfile.TemporaryDirectory() as wd:
            real_mkstemp = tempfile.mkstemp
            paths = []

            def record_log(*args, **kwargs):
                fd, path = real_mkstemp(*args, **kwargs)
                paths.append(path)
                return fd, path

            with patch.object(sandbox.tempfile, "mkstemp", side_effect=record_log):
                self.assertEqual(sandbox.execute("true", wd), (0, ""))
                with self.assertRaises(OSError):
                    sandbox.execute("true", str(Path(wd, "missing")))
            self.assertEqual(len(paths), 2)
            self.assertTrue(all(not Path(path).exists() for path in paths))


if __name__ == "__main__":
    unittest.main()
