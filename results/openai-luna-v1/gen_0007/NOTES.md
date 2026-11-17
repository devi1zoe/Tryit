Parent gen_0006 passed 16/16; available traces showed avoidable failures from assuming Git was available, not failed benchmark outcomes.
Enabled Bash inherit_errexit after reproducing a command substitution that hid a failed check behind a later successful command.
Updated the prompt to explain safe substitution capture and checking for Git before relying on repository commands or exact-change comparisons.
Added offline regressions for nested/pipeline substitutions, successful and explicitly handled failures, and completion-checkpoint recovery through a scripted agent.
Validation: 39 offline tests pass; all 56 shell commands from the 81 parent replies pass syntax checks with the new Bash options.
Public signatures, approval policy, parser, output logging, and completion rules are unchanged; no model calls or online evaluation were performed.
