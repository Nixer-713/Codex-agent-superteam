# Maturity Roadmap

Codex Agent Superteam is moving from a local task-loop MVP toward a recoverable, GitHub-backed multi-agent automation system.

## Release Milestones

| Milestone | Status | Focus |
|---|---:|---|
| v0.1 local gates | complete | local task loop, Git diff evidence, scope and review gates |
| v0.2 superteam framework | complete | state/resume, config, review loop, GitHub issue/PR helpers, privacy scan, final reports |
| v0.3 multi-agent orchestration | complete | worktree-aware orchestration, path conflict blocking, lifecycle evidence |
| v0.4 parallel runner | complete | process-based worker launch, stdout/stderr logs, exit codes, duration, richer reports |
| v0.5 review revise loop | current | GitHub review comments, revise decisions, attempt prompts, report feedback |

## Completed Capabilities

- Local task queue and run artifacts.
- Bounded Codex worker prompts and mailbox completion signals.
- Diff capture, scope checks, risk reports, validation records, and review files.
- Worktree merge evidence gates.
- GitHub draft PR creation, PR body sync, CI watch, and PR check evidence.
- GitHub Actions test workflow.
- Resumable run state via `state` and `resume`.
- Project configuration via `.agent-loop/config.yaml`.
- Review decisions and revision prompts.
- GitHub issue import from deterministic issue JSON.
- Privacy scanning and release checks.
- Final run reports.
- Conservative multi-agent path conflict detection.

## v0.4 Acceptance

- `orchestrate --parallel` starts unique workers and writes lifecycle evidence.
- `orchestrate --worktree` records per-worker worktree metadata.
- `orchestrate --run-codex --watch` can launch and wait on multiple worker processes.
- `orchestrate --run-command` supports deterministic runner tests and custom wrappers.
- Each worker records `pid`, `exit_code`, `duration_seconds`, `worker.stdout.log`, and `worker.stderr.log`.
- Worker failures are isolated and summarized without stopping unrelated workers.
- `state` and `report` surface worker status, exit code, failure reason, and log paths.
- `orchestrate-report.md` lists started, blocked, failed, review-ready workers, and next recommended commands.
- Human gates remain intact: no automatic `review-accept`, `worktree-apply`, `accept`, PR merge, or high-risk override.


## v0.5 Acceptance

- `github-pr-comments --from-file` imports deterministic PR review JSON into yaml and markdown evidence.
- Empty PR comment imports do not force a revise decision.
- `review-result --from-github-comments` writes `decision: revise` only when imported comments exist.
- `accept` remains blocked while review decision is `revise`.
- `revise` writes a new `attempts/<attempt-id>.revise.prompt.md` without overwriting prior attempts.
- Revision prompts include parent run id, original task scope, changed files, GitHub comment paths, lines, and bodies.
- `report` includes GitHub review feedback and recommends `revise` while feedback is unresolved.

## Future Work

- Durable daemon mode for long-running orchestration across terminal restarts.
- PR review comment ingestion that automatically generates revise attempts.
- Richer conflict resolution beyond conservative path-prefix checks.
- Dashboard or TUI for active workers, evidence gaps, and PR status.
- Signed releases and package publishing.
- Pluggable worker backends beyond Codex CLI.
- Optional policy engine for team-specific risk thresholds and approval rules.

## Public Template Rules

- Documentation should use `$PROJECT_ROOT`, `/path/to/project`, and `https://github.com/<owner>/<repo>.git` placeholders.
- Do not commit local run artifacts such as `.agent-runs/`, `.tasks/`, `.locks/`, or `.agent-loop/` runtime state.
- Run `agent-loop privacy-scan --root .` and `agent-loop release-check --root .` before release PRs.
