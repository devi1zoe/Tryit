"""Seed harness (generation 0).

Everything in this package can be rewritten by the RSI loop: prompts and context
management, action parsing, the approval policy, the inner sandbox and the agent loop.

Contract the outer loop relies on (keep these two names and signatures):
    run_agent(task: str, workdir: str, llm, limits: dict) -> dict
        llm(system: str, messages: list[{"role", "content"}]) -> str
        Raises an exception when the outer process refuses a call (e.g. call limit).
        limits: {"max_llm_calls": int, ...} as set by the outer loop.
        Return a JSON-serialisable dict; "status" should be "submitted" when done.
    check_action(command: str, workdir: str) -> (allowed: bool, reason: str)
        The approval decision for a shell command. The outer loop probes it with a
        fixed set of dangerous and benign commands to track safety across generations.
"""
from .agent import run_agent
from .approval import check_action

__all__ = ["run_agent", "check_action"]
