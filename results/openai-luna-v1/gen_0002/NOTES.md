Parent failures were premature submissions: no implementation or requested output existed, despite one reply claiming tests passed.
Added content-based workspace tracking and a completion checkpoint requiring executed work and a successful command after the latest edit.
Rejected submissions show concrete changed-file evidence and request missing implementation/verification; read-only tasks have an explicit verified no-change path.
Strengthened the prompt to distinguish planned from executed work, verify the full requested scope, and inspect large files selectively.
Bound observations to 5,000 characters with an explicit truncation warning; approval rules and public entry-point signatures are unchanged.
Validated offline with 11 scripted-agent regression tests covering early-submit recovery, failed checks, read-only work, snapshots, parsing, budgets, and approval behavior.
