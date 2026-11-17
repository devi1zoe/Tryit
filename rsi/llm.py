"""LLM access for the outer (trusted) process.

The harness under evolution never talks to a model provider directly: it runs in a
network-less child process and sends requests over a pipe. Calls are made here, so
the outer loop controls which model is used and how much is spent.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

# USD per 1M tokens (input, output). Used only for budget accounting.
PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-2": (8.0, 40.0),
}


class BudgetExceeded(RuntimeError):
    pass


class LLMError(RuntimeError):
    pass


@dataclass
class ModelSpec:
    provider: str = "anthropic"  # anthropic | litellm | scripted
    name: str = "claude-opus-5-5"
    effort: str | None = "medium"
    max_tokens: int = 16000
    # Server-side refusal fallback (Anthropic). Note for experiments: when it fires,
    # a different model answered that turn; this is recorded per call as `served_model`.
    fallbacks: Any = "default"
    responses: list[str] = field(default_factory=list)  # scripted provider only

    @classmethod
    def from_dict(cls, d: dict) -> "ModelSpec":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def label(self) -> str:
        return f"{self.provider}:{self.name}" + (f"@{self.effort}" if self.effort else "")


class Budget:
    """Thread-safe global spend tracker shared by every call in an experiment."""

    def __init__(self, limit_usd: float | None = None, spent_usd: float = 0.0):
        self.limit_usd = limit_usd
        self.spent_usd = spent_usd
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0
        self._lock = threading.Lock()

    def check(self):
        if self.limit_usd is not None and self.spent_usd >= self.limit_usd:
            raise BudgetExceeded(f"budget exhausted: ${self.spent_usd:.2f} >= ${self.limit_usd:.2f}")

    def add(self, model: str, inp: int, out: int) -> float:
        pin, pout = PRICES.get(model, (0.0, 0.0))
        cost = inp / 1e6 * pin + out / 1e6 * pout
        with self._lock:
            self.spent_usd += cost
            self.input_tokens += inp
            self.output_tokens += out
            self.calls += 1
        return cost

    def snapshot(self) -> dict:
        return {"spent_usd": round(self.spent_usd, 4), "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "calls": self.calls, "limit_usd": self.limit_usd}


class LLMClient:
    def __init__(self, spec: ModelSpec, budget: Budget):
        self.spec = spec
        self.budget = budget
        self._client = None
        if spec.provider == "anthropic":
            import anthropic

            self._anthropic = anthropic
            self._client = anthropic.Anthropic(max_retries=4)
        elif spec.provider == "litellm":
            try:
                import litellm  # optional dependency
            except ImportError as e:  # pragma: no cover
                raise LLMError("provider 'litellm' needs `pip install litellm`") from e
            self._litellm = litellm
        elif spec.provider != "scripted":
            raise LLMError(f"unknown provider {spec.provider!r}")

    def complete(self, system: str, messages: list[dict]) -> dict:
        """Return {text, input_tokens, output_tokens, cost, served_model, stop_reason}."""
        self.budget.check()
        messages = _sanitize(messages)
        p = self.spec.provider
        if p == "scripted":
            return self._scripted(messages)
        if p == "anthropic":
            return self._call_anthropic(system, messages)
        return self._call_litellm(system, messages)

    # -- providers -------------------------------------------------------------------
    def _call_anthropic(self, system: str, messages: list[dict]) -> dict:
        a = self._anthropic
        kwargs: dict[str, Any] = dict(model=self.spec.name, max_tokens=self.spec.max_tokens,
                                      system=system, messages=messages)
        if self.spec.effort:
            kwargs["output_config"] = {"effort": self.spec.effort}
        try:
            if self.spec.fallbacks:
                resp = self._client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks=self.spec.fallbacks, **kwargs)
            else:
                resp = self._client.messages.create(**kwargs)
        except a.RateLimitError as e:
            raise LLMError(f"rate limited: {e}") from e
        except a.APIStatusError as e:
            raise LLMError(f"API error {e.status_code}: {e.message}") from e
        except a.APIConnectionError as e:
            raise LLMError(f"connection error: {e}") from e
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        if resp.stop_reason == "refusal":
            text = text or "[the model declined to respond]"
        u = resp.usage
        inp = (u.input_tokens or 0) + (getattr(u, "cache_read_input_tokens", 0) or 0) + \
              (getattr(u, "cache_creation_input_tokens", 0) or 0)
        out = u.output_tokens or 0
        cost = self.budget.add(self.spec.name, inp, out)
        return {"text": text, "input_tokens": inp, "output_tokens": out, "cost": cost,
                "served_model": resp.model, "stop_reason": resp.stop_reason}

    def _call_litellm(self, system: str, messages: list[dict]) -> dict:  # pragma: no cover
        lm = self._litellm
        try:
            resp = lm.completion(model=self.spec.name, max_tokens=self.spec.max_tokens,
                                 messages=[{"role": "system", "content": system}] + messages)
        except Exception as e:
            raise LLMError(f"litellm error: {e}") from e
        text = resp.choices[0].message.content or ""
        inp, out = resp.usage.prompt_tokens, resp.usage.completion_tokens
        try:
            cost = float(lm.completion_cost(completion_response=resp))
        except Exception:
            cost = 0.0
        with self.budget._lock:
            self.budget.spent_usd += cost
            self.budget.input_tokens += inp
            self.budget.output_tokens += out
            self.budget.calls += 1
        return {"text": text, "input_tokens": inp, "output_tokens": out, "cost": cost,
                "served_model": self.spec.name, "stop_reason": resp.choices[0].finish_reason}

    def _scripted(self, messages: list[dict]) -> dict:
        """Deterministic offline model for tests: the i-th assistant turn of every
        conversation gets responses[i]; past the end it submits."""
        i = sum(1 for m in messages if m["role"] == "assistant")
        r = self.spec.responses
        text = r[i] if i < len(r) else "Done.\n```bash\necho SUBMIT\n```"
        self.budget.add(self.spec.name, 0, 0)
        return {"text": text, "input_tokens": 0, "output_tokens": 0, "cost": 0.0,
                "served_model": "scripted", "stop_reason": "end_turn"}


def _sanitize(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        role = m.get("role")
        if role not in ("user", "assistant"):
            raise LLMError(f"invalid role {role!r}")
        content = m.get("content")
        if not isinstance(content, str):
            raise LLMError("message content must be a string")
        out.append({"role": role, "content": content if content.strip() else "(empty)"})
    if not out or out[0]["role"] != "user":
        raise LLMError("conversation must start with a user message")
    return out
