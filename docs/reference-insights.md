# Reference Insights For Codex Agent Loop

## 1. Karpathy Coding Guidelines

Stored as `protocols/karpathy-coding-guidelines.md` and treated as a bottom execution logic layer. The practical effect is to bias workers toward explicit assumptions, minimal implementation, surgical diffs, and verified goals.

## 2. obra/superpowers

Reference: `https://github.com/obra/superpowers`

Borrowed ideas:

- Skills as enforceable workflows, not passive advice.
- Brainstorm/spec before implementation for non-trivial work.
- Implementation plans with checkboxes and concrete verification steps.
- TDD for features and bug fixes.
- Verification before claiming completion.
- Review loops before merge/commit.

How this maps into Codex Agent Loop:

- `protocols/execution-protocol.md` defines the baseline worker/reviewer rules.
- `docs/superpowers/plans/` stores implementation plans.
- `review.md` and `scope-check.yaml` make verification explicit before `accept`.
- Future commands should use policy gates instead of relying only on model memory.

## 3. Yeachan-Heo/oh-my-codex

Reference: `https://github.com/Yeachan-Heo/oh-my-codex`

Borrowed ideas:

- A state directory similar to `.omx` for shared runtime truth.
- Role surfaces: different prompts/instructions for planner, worker, reviewer, and operator.
- Doctor/HUD-style diagnostics for setup and current project state.
- Hooks and scripts around Codex rather than changing Codex internals.
- Team runtime concepts using tmux/worktrees for long-running or parallel work.

How this maps into Codex Agent Loop:

- `.agent-loop/`, `.agent-runs/`, `.tasks/`, and `.locks/` are the local state layer.
- `dispatch` creates role-specific worker prompts.
- `advance` is the first hook-like lifecycle command.
- Future `doctor`, `hud`, `watch`, and `worktree` commands can make the system more autonomous without removing human approval gates.

## 4. Near-Term Enhancements

1. Add `doctor` to verify Git repo, user config, writable paths, pending/active task consistency, and placeholder path mistakes.
2. Add role prompt templates for planner, worker, reviewer, and operator.
3. Add `watch` to wait for mailbox done/blocked signals and then run `advance` automatically.
4. Add `blocked` command so workers can stop safely with structured reasons.
5. Add patch-size risk scoring before review.
6. Add worktree support for parallel workers.
