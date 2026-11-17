"""Ground completion decisions in executions and actual workspace contents."""
import hashlib
import os
import stat

# Interpreter/tool caches are not task deliverables or evidence of an edit.
_IGNORED_DIRS = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}


def snapshot(workdir):
    """Content fingerprints, without following links or opening special files."""
    result = {}
    for root, dirs, files in os.walk(workdir, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in _IGNORED_DIRS)
        links = [d for d in dirs if os.path.islink(os.path.join(root, d))]
        dirs[:] = [d for d in dirs if d not in links]
        for name in sorted(files + links):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, workdir)
            try:
                info = os.lstat(path)
                if stat.S_ISLNK(info.st_mode):
                    result[rel] = ("link", os.readlink(path))
                elif stat.S_ISREG(info.st_mode):
                    digest = hashlib.sha256()
                    with open(path, "rb") as stream:
                        for chunk in iter(lambda: stream.read(131072), b""):
                            digest.update(chunk)
                    result[rel] = ("file", stat.S_IMODE(info.st_mode), digest.hexdigest())
            except OSError:
                # Unreadable files should not prevent the agent from working.
                result[rel] = ("unreadable",)
    return result


class CompletionTracker:
    def __init__(self, workdir):
        self.workdir = workdir
        self.initial = snapshot(workdir)
        self.current = self.initial
        self.executions = 0
        self.last_change = 0
        self.last_success = 0
        self.last_returncode = None
        self.review_at = None
        self.no_changes_check = None

    def observe(self, returncode, output=""):
        self.executions += 1
        current = snapshot(self.workdir)
        if current != self.current:
            self.last_change = self.executions
        self.current = current
        self.last_returncode = returncode
        if returncode == 0:
            self.last_success = self.executions
            if "NO_CHANGES_NEEDED" in output.splitlines():
                self.no_changes_check = self.executions

    def changes(self):
        created = sorted(self.current.keys() - self.initial.keys())
        deleted = sorted(self.initial.keys() - self.current.keys())
        modified = sorted(p for p in self.current.keys() & self.initial.keys()
                          if self.current[p] != self.initial[p])
        lines = []
        for label, paths in (("Created", created), ("Modified", modified), ("Deleted", deleted)):
            if paths:
                shown = ", ".join(repr(p) for p in paths[:15])
                if len(shown) > 1500:
                    shown = shown[:1500] + "..."
                extra = f" (+{len(paths) - 15} more)" if len(paths) > 15 else ""
                lines.append(f"{label}: {shown}{extra}")
        return "\n".join(lines) if lines else "No task files have changed from the starting workspace."

    def submission_feedback(self):
        """None means accept; otherwise request an evidence-producing command.

        Successful commands after the last edit count as verification evidence,
        not proof of correctness. No task-specific tests or filenames are assumed.
        """
        changed = self.current != self.initial
        verified = (self.last_returncode == 0
                    and self.last_success > self.last_change)
        # Read-only tasks are valid, but must explicitly pass a completion review.
        reviewed = (self.review_at is not None
                    and self.no_changes_check is not None
                    and self.no_changes_check > self.review_at)
        if verified and (changed or reviewed):
            return None
        self.review_at = self.executions
        reasons = []
        if not self.executions:
            reasons.append("No shell commands have been executed.")
        elif self.last_returncode != 0:
            reasons.append("The last executed command did not succeed.")
        if not changed:
            reasons.append("No deliverable changes are recorded. Inspection is not implementation.")
        if not verified:
            reasons.append("There is no successful verification command after the latest edit.")
        return (
            "Completion checkpoint: NOT submitted.\n"
            + "\n".join(reasons) + "\nWorkspace evidence:\n" + self.changes()
            + "\nOnly fenced shell commands that actually ran affect the workspace; "
              "claims in a reply do not create files or run tests.\n"
              "Re-read the task and finish any missing work. Then run a separate, "
              "task-relevant verification command and inspect its result before submitting again. "
              "Check required output files exist and their contents are correct; for code, "
              "run the relevant tests and check edge cases. If the task is read-only or "
              "already satisfied, run a command that verifies the original requirements and, "
              "only if it succeeds, prints the exact line NO_CHANGES_NEEDED to acknowledge "
              "that no deliverable changes are required. Then submit again; no gratuitous edit is needed."
        )
