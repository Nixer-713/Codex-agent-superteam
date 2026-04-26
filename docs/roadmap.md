# Maturity Roadmap

Codex Agent Superteam is moving from a local task-loop MVP toward a recoverable, GitHub-backed multi-agent automation system.

## Release Milestones

| Milestone | Status | Focus |
|---|---:|---|
| v0.1 local gates | complete | local task loop, Git diff evidence, scope and review gates |
| v0.2 superteam framework | complete | state/resume, config, review loop, GitHub issue/PR helpers, privacy scan, final reports |
| v0.3 multi-agent orchestration | complete | worktree-aware orchestration, path conflict blocking, lifecycle evidence |
| v0.4 parallel runner | complete | process-based worker launch, stdout/stderr logs, exit codes, duration, richer reports |
| v0.5 review revise loop | complete | GitHub review comments, revise decisions, attempt prompts, report feedback |
| v0.6 durable orchestrator | complete | persistent orchestration state and safe resume to review boundary |
| v0.7 public template hardening | complete | template init, redacted privacy evidence, release readiness reports |
| v0.8 usability self-test | complete | one-command temporary smoke test for install readiness |
| v0.9 quickstart wrapper | current | safe shell script for one-command setup and bounded task start |

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


## v0.6 Acceptance

- `orchestrate` writes `.agent-loop/orchestrator-state.yaml` with orchestration id, parallelism, worker ids, run ids, statuses, logs, pids, exit codes, and `last_seen_at`.
- `orchestrate-state` prints current durable state without crossing any gate.
- `resume-orchestrate --watch` advances done workers to review-ready evidence.
- Failed and blocked workers are summarized without stopping unrelated workers.
- `resume-orchestrate` does not run `review-accept`, `worktree-apply`, `accept`, or GitHub merge.


## v0.7 Acceptance

- `template-init` creates generic `.agent-loop/config.yaml` and optional GitHub issue/PR templates.
- Generated templates use `$PROJECT_ROOT` placeholders and no local machine paths.
- `privacy-scan` redacts token-like matches in evidence.
- `release-check` writes both `release-check.yaml` and `release-check.md`.
- Release checks include privacy, package version, version tag, and README presence.


## v0.8 Acceptance

- `self-test` creates a temporary Git project and does not mutate the caller project.
- `self-test` runs template initialization, task creation, completion evidence, safe resume, review evidence, and privacy scan.
- `self-test` exits 0 and prints the generated temporary evidence paths when the framework is ready to use.

## v0.9 Acceptance

- `scripts/agent-loop-quickstart.sh --init-only` runs self-test, init, template-init, and doctor.
- The script can create a scoped task and start orchestration without accepting or merging changes.
- `--run-codex` and `--watch` are explicit opt-ins.

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
