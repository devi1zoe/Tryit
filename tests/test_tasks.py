import shutil

import pytest

from conftest import isolation
from reference_solutions import SOLUTIONS
from rsi.tasks import load_tasks

TASKS = load_tasks("all")


def test_every_task_has_reference_solution():
    assert {t.id for t in TASKS} == set(SOLUTIONS)


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_untouched_workspace_fails(task):
    wd = task.prepare()
    assert not task.grade(wd, isolation())["passed"]
    shutil.rmtree(wd)


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_reference_solution_passes(task):
    wd = task.prepare()
    SOLUTIONS[task.id](wd)
    g = task.grade(wd, isolation())
    assert g["passed"], g["check_output"]
    shutil.rmtree(wd)


def test_early_exit_cannot_fake_a_pass():
    task = next(t for t in TASKS if t.id == "fix_stats")
    wd = task.prepare()
    (wd / "stats.py").write_text("import os\nprint('PASS 0000')\nos._exit(0)\n")
    assert not task.grade(wd, isolation())["passed"]
