from types import SimpleNamespace

import pytest

from rsi.llm import Budget, LLMClient, LLMError, ModelSpec


class FakeCompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kw):
        self.kwargs = kw
        return SimpleNamespace(
            model=kw["model"],
            choices=[SimpleNamespace(message=SimpleNamespace(content="pong", refusal=None), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=100_000))


def test_openai_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    b = Budget(limit_usd=10)
    c = LLMClient(ModelSpec(provider="openai", name="gpt-6.1-sol", effort="high", price=[2.0, 10.0]), b)
    fake = FakeCompletions()
    c._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    r = c.complete("sys", [{"role": "user", "content": "ping"}])
    assert r["text"] == "pong" and r["cost"] == pytest.approx(3.0)
    assert fake.kwargs["messages"][0] == {"role": "system", "content": "sys"}
    assert fake.kwargs["reasoning_effort"] == "high"
    assert b.spent_usd == pytest.approx(3.0)


def test_openai_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMError):
        LLMClient(ModelSpec(provider="openai", name="gpt-6-luna"), Budget())


def test_budget_cap():
    b = Budget(limit_usd=1, spent_usd=1.5)
    c = LLMClient(ModelSpec(provider="scripted", name="s"), b)
    with pytest.raises(Exception, match="budget"):
        c.complete("s", [{"role": "user", "content": "x"}])
