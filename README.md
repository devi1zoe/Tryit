# Tryit: recursive self-improvement of agent harnesses

A minimal research framework where an LLM agent rewrites **its own harness**: the code
between the model and its tools (prompting and context, action parsing, the approval
policy, the inner sandbox, the agent loop). The outer loop is in the style of the
Darwin Gödel Machine (open-ended archive, self-referential proposer) and Meta-Harness
(the proposer reads the full history of code, scores and traces from files).

An **agent = model × harness**. Any model (Anthropic natively, others through LiteLLM)
can be paired with any harness generation from any experiment.

This is the deliberately small first version: 8 quick benchmark tasks, one cloud
container, no Docker. Scale-up items are listed at the end.

## Layout

```
harness/      seed harness, generation 0 (everything here is editable by the RSI loop)
  agent.py      loop: model -> parse -> approve -> execute -> observe
  context.py    system prompt, observation formatting and truncation
  tools.py      action parsing (one ```bash block per turn)
  approval.py   approval policy: check_action(command, workdir) -> (allowed, reason)
  sandbox.py    inner sandbox: how approved commands run
rsi/          outer loop (trusted; the harness can neither see nor change it)
  llm.py        model clients + global budget; all model calls happen here
  runner.py     outer containment: runs a harness in an isolated child process
  child.py      child entry point; proxies model calls over a pipe
  tasks.py      benchmark loading and hidden grading
  evaluate.py   evaluate (model, harness) on tasks
  proposer.py   proposal step: an agent edits a copy of the parent harness
  archive.py    DGM-style archive and parent selection
  evolve.py     the loop
  report.py     markdown report
safety/       fixed safety instrumentation (trusted)
  probes.py     22 dangerous + 15 benign commands posed to each generation's check_action
  audit.py      per-generation diff, "safety files touched", red-flag code patterns
  integrity.py  fingerprint of trusted code, verified every generation
benchmarks/tasks/   8 tasks: gen.py builds the workspace, check.py grades (hidden)
configs/      agent configs (model + harness) and experiment configs
tests/        offline tests (scripted model; no API key needed)
```

## Two layers of containment

| | Inner (under study) | Outer (fixed) |
|---|---|---|
| Code | `harness/approval.py`, `harness/sandbox.py` | `rsi/runner.py`, `safety/` |
| Editable by RSI | yes | no, and not even visible |
| Mechanism | regex policy, subprocess with timeout | user + mount + network namespaces (`unshare -rnm`): no network, repository, `/root` and graders hidden behind empty tmpfs, harness code read-only, rlimits, wall-clock kill |
| Model access | none directly | model calls proxied through the parent, which enforces call, token and USD caps and records the trusted transcript |

Optimisation pressure acts only on the task score. The inner policy can therefore drift,
and that drift is measured, not prevented (unless you turn on a gate):

- `dangerous_block_rate` / `benign_allow_rate` from `safety/probes.py`, every generation.
  The probe set is never shown to the proposer (held out, like a test set).
- `sensitive_touched`: whether a proposal edited `approval.py` / `sandbox.py`.
- `red_flags`: new code patterns such as references to grading internals, process
  inspection, network code, unconditional approval.
- `selection.safety_gate`: `off` (observe only), `no_regression` (children whose block
  rate falls below the seed's cannot be selected as parents), or `min`.

Grading cannot be faked by exiting early: the checker must print a per-run random nonce.

## Usage

```bash
pip install anthropic pyyaml pytest   # run everything from the repo root
python -m pytest -q               # offline tests

python -m rsi probe                                    # safety probes of the seed harness
python -m rsi run  --agent configs/agents/haiku55-seed.yaml --task fix_stats --show
python -m rsi eval --agent configs/agents/opus55-seed.yaml
python -m rsi evolve --config configs/evolve/haiku-smoke.yaml   # cheap end-to-end check
python -m rsi evolve --config configs/evolve/small.yaml         # the real experiment
python -m rsi report runs/small-v1
```

Results go to `runs/<experiment>/`: `archive/gen_XXXX/` holds each generation's
`harness/`, `meta.json`, `eval.json`, `probes.json`, `audit.json`, `patch.diff`,
`NOTES.md`, the proposer's run, and per-task `traces/`. `report.md` summarises.

The anthropic provider needs `ANTHROPIC_API_KEY` (or another credential the SDK can find).
`budget_usd` in the experiment config is a hard cap.

### Choosing models

`fallbacks: default` enables Anthropic's server-side refusal fallback: when the model
declines a request, another model answers that turn. Every model that actually served
a call is recorded (`served_models`). Set `fallbacks: null` if a single fixed model
matters for your comparison.

## Known limits of v1 (scale-up list)

- Namespaces are weaker than gVisor/Firecracker; the child runs as (namespaced) root and
  can see the rest of the filesystem outside the hidden paths (but has no network).
- Probes test `check_action` statically; `sandbox.py` changes are only diffed and flagged.
- 8 tasks and `repeats: 1` make selection noisy and easy to overfit; add a held-out split
  (`split:` in task.yaml) and repeats.
- Generations run sequentially; DGM runs proposals in parallel.
- Benchmarks to add later: SWE-bench Lite / Verified, Terminal-Bench 2.
- Related work to compare against: DGM, Huxley-Gödel Machine, Meta-Harness, SICA,
  ADAS, Gödel Agent, AFlow, OpenEvolve.
