# Maturity Roadmap

Codex Agent Superteam is moving from a local task-loop MVP toward a recoverable, GitHub-backed multi-agent automation system.

## Completed

- Local task queue and run artifacts.
- Bounded Codex worker prompts and mailbox completion signals.
- Diff capture, scope checks, risk reports, validation records, and review files.
- Worktree merge evidence gates.
- GitHub draft PR creation, PR body sync, CI watch, and PR check evidence.
- GitHub Actions test workflow.
- `v0.1.0-local-github-gates` milestone tag.

## Current Development Track

- Resumable run state via `state` and `resume`.
- Project configuration via `.agent-loop/config.yaml`.
- Basic multi-task orchestration via `orchestrate`.
- Review decisions and revision prompts.
- GitHub issue import from deterministic issue JSON.
- Privacy scanning and release checks.
- Final run reports.

## Future Work

- Fully parallel Codex execution across worktrees. (v0.3 introduces worktree-aware orchestration evidence and watch handling.)
- PR review comment ingestion for automated revise loops.
- Rich conflict resolution between multiple workers.
- Package publishing and signed releases.
- Web or terminal dashboard for run status.

## v0.3 Acceptance

- `orchestrate --parallel` starts unique workers and writes lifecycle evidence.
- `orchestrate --worktree` records per-worker worktree metadata.
- Path ownership conflicts are blocked before worker launch.
- `orchestrate --watch` summarizes done, blocked, failed, and review-ready workers without crossing human gates.
