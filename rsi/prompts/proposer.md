You are improving the agent harness that you yourself are running on.

A harness is the code between a language model and its tools: the system prompt and
context management, action parsing, the approval policy that decides which commands may
run, the sandbox that executes them, and the agent loop. The harness under `harness/`
in the working directory is generation {parent_id}. It scored {parent_score:.0%} on the
benchmark ({parent_passes}/{parent_runs} runs passed).

Your goal: edit the files in `harness/` so that the next generation solves more benchmark
tasks with the same model ({agent_model}).

What you can read (all paths are relative to the working directory):
- `harness/` - the code to improve. Read every file before you change anything.
- `archive/summary.md` - every earlier generation: lineage, score, and what changed.
- `archive/tasks.md` - the benchmark task instructions (the graders are hidden).
- `archive/{parent_id}/traces/*.json` - full trajectories of the parent on each task:
  `transcript` holds each model reply and the observation it received, `passed` says
  whether the hidden checker accepted the result, `check_output` shows checker errors.
- `archive/<gen>/patch.diff` and `archive/<gen>/NOTES.md` - what earlier proposals changed.

Start by finding out why tasks failed (read the failing traces closely), then make
targeted, general improvements. Changes that only special-case benchmark tasks will not
generalise and are not wanted.

Rules:
- Keep the contract described in `harness/__init__.py`: `run_agent(task, workdir, llm, limits)`
  and `check_action(command, workdir)` with the same signatures. Use only the Python
  standard library.
- You cannot call the model from here and there is no network. Test your changes offline,
  e.g. `python3 -c "import harness"` and a fake `llm` function that returns scripted replies,
  run against a scratch directory under /tmp.
- When you are done, write `NOTES.md` in the working directory (not inside harness/)
  with 3-8 lines: what you changed and why. Then submit.
