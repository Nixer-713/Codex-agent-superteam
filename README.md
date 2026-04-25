# Codex Agent Superteam

A local-first automation framework for running Codex as a bounded, reviewable, Git-backed agent team.

Codex Agent Superteam turns ad-hoc coding sessions into an auditable loop:

```text
Task → bounded worker prompt → Codex execution → mailbox signal → diff capture → scope check → review → GitHub PR → CI → human merge decision
```

It is designed for large projects where you need automation, but still want clear evidence before accepting code.

## What It Provides

- **Task queue**: file-based pending/active/done tasks with allowed and forbidden path scopes.
- **Bounded workers**: generated Codex worker prompts with explicit ownership, stop conditions, and completion files.
- **Local review gates**: Git diff capture, scope checks, risk reports, validation records, and review artifacts.
- **Worktree isolation**: run multiple workers in separate Git worktrees before applying changes back.
- **GitHub audit layer**: draft PR creation, PR body evidence sync, CI watching, and PR acceptance checks.
- **Human final control**: the system prepares evidence; it does not auto-merge PRs.


## Installation

Use the repository directly during development:

```bash
git clone https://github.com/<owner>/codex-agent-superteam.git
cd codex-agent-superteam
python3 -m pip install -e .
agent-loop --help
```

Or run without installing:

```bash
python3 -m agent_loop.cli --help
```

## Quick Start

Clone this repository, then run the CLI against any Git project you want Codex to work on:

```bash
git clone https://github.com/<owner>/codex-agent-superteam.git
cd codex-agent-superteam

export PROJECT_ROOT="/absolute/path/to/your/project"
python3 -m agent_loop.cli init --root "$PROJECT_ROOT"
python3 -m agent_loop.cli doctor --root "$PROJECT_ROOT"
```

Create and run a bounded task:

```bash
python3 -m agent_loop.cli new-task "Add login validation" \
  --root "$PROJECT_ROOT" \
  --allowed 'src/auth/**' \
  --forbidden 'infra/**' \
  --validation 'python3 -m pytest'

RUN_ID=$(python3 -m agent_loop.cli run-next --root "$PROJECT_ROOT" | awk '{print $2}')
python3 -m agent_loop.cli dispatch "$RUN_ID" --root "$PROJECT_ROOT" --agent-id worker-auth --codex-command
python3 -m agent_loop.cli run-codex "$RUN_ID" --root "$PROJECT_ROOT" --agent-id worker-auth --dry-run
python3 -m agent_loop.cli watch "$RUN_ID" --root "$PROJECT_ROOT" --agent-id worker-auth --timeout 300
```

Review and accept only after evidence is ready:

```bash
python3 -m agent_loop.cli status --root "$PROJECT_ROOT"
python3 -m agent_loop.cli accept "$RUN_ID" --root "$PROJECT_ROOT" --commit
```

## Safe Automation Boundary

The framework automates mechanical work:

- task and run artifact creation
- bounded Codex prompt generation
- worker done/blocked detection
- Git diff capture
- scope checking
- risk and validation evidence
- review file generation
- GitHub PR body generation and sync
- GitHub Actions waiting and PR check evidence

It keeps uncertain decisions human-controlled:

- scope expansion
- high-risk patch acceptance
- final commit acceptance
- PR merge decisions
- failed validation overrides

## Worktree Merge Gate

For parallel workers, use one worktree per agent:

```bash
python3 -m agent_loop.cli worktree-start "$RUN_ID" \
  --root "$PROJECT_ROOT" \
  --agent-id worker-docs \
  --path ../project-worker-docs
```

A worktree run must pass the full merge evidence chain before `accept --commit`:

```bash
python3 -m agent_loop.cli worktree-collect "$RUN_ID" --root "$PROJECT_ROOT" --agent-id worker-docs
python3 -m agent_loop.cli merge-preflight "$RUN_ID" --root "$PROJECT_ROOT" --agent-id worker-docs
python3 -m agent_loop.cli worktree-preview "$RUN_ID" --root "$PROJECT_ROOT" --agent-id worker-docs
python3 -m agent_loop.cli review-accept "$RUN_ID" --root "$PROJECT_ROOT" --agent-id worker-docs
python3 -m agent_loop.cli worktree-apply "$RUN_ID" --root "$PROJECT_ROOT" --agent-id worker-docs
python3 -m agent_loop.cli accept "$RUN_ID" --root "$PROJECT_ROOT" --commit
```

Required evidence includes:

```text
.agent-runs/<run-id>/
  worktrees.yaml
  worktree-collect.yaml
  merge-preflight.yaml
  changed-files.txt
  diff-stat.txt
  diff.patch
  scope-check.yaml
  risk.yaml
  validation.yaml
  review.md
  review-decision.yaml
  post-apply-diff.patch
  merge-result.yaml
  mailbox/<agent-id>.done.md
```

## GitHub Workflow

After local evidence is ready, use GitHub as the remote review and debugging layer:

```bash
python3 -m agent_loop.cli github-doctor --root "$PROJECT_ROOT"
python3 -m agent_loop.cli github-pr-body "$RUN_ID" --root "$PROJECT_ROOT"
python3 -m agent_loop.cli github-pr-create "$RUN_ID" --root "$PROJECT_ROOT" --draft
python3 -m agent_loop.cli github-pr-sync "$RUN_ID" --root "$PROJECT_ROOT"
python3 -m agent_loop.cli github-ci-watch --root "$PROJECT_ROOT" --timeout 600 --poll 10
python3 -m agent_loop.cli github-pr-check "$RUN_ID" --root "$PROJECT_ROOT"
```

### GitHub Acceptance Evidence

`github-pr-check` writes `github-pr-check.yaml` and verifies:

- the PR is open
- the PR is not draft
- PR files match local `changed-files.txt`
- GitHub status checks are complete and successful

`github-ci-watch` writes `.agent-loop/github-ci-watch.yaml` with the current commit SHA, run IDs, conclusions, and run URLs.

The system still does **not** merge PRs automatically. GitHub remains the final human review surface: Files changed, commits, CI logs, review comments, blame, compare, and revert.

## Repository CI

This template includes GitHub Actions at `.github/workflows/test.yml`.

The workflow runs on pull requests and on pushes to `main` or `codex/**` branches:

```bash
python3 -m pytest -q
```



## v0.3 Multi-Agent Orchestration

Use `orchestrate` to start several scoped workers at once while keeping human gates intact:

```bash
agent-loop orchestrate \
  --root "$PROJECT_ROOT" \
  --parallel 3 \
  --worktree \
  --watch
```

The orchestrator assigns unique worker ids, creates per-run evidence, optionally creates Git worktrees, and writes `.agent-loop/orchestrate-result.yaml` plus `.agent-loop/orchestrate-report.md`. It does not run `accept`, `worktree-apply`, or merge GitHub PRs. If task ownership paths overlap, the safer default is to block the conflicting task and record it in the orchestrate report.

## Maturity Roadmap

The current template includes the local task loop, worktree gates, GitHub PR/CI gates, resumable state inspection, privacy scanning, release checks, and final reports. See `docs/roadmap.md` for the maturity roadmap and remaining automation work.

Key newer commands:

```bash
agent-loop state "$RUN_ID" --root "$PROJECT_ROOT"
agent-loop resume "$RUN_ID" --root "$PROJECT_ROOT"
agent-loop orchestrate --root "$PROJECT_ROOT" --parallel 2
agent-loop review-result "$RUN_ID" --root "$PROJECT_ROOT" --decision revise --reason "..."
agent-loop revise "$RUN_ID" --root "$PROJECT_ROOT" --agent-id worker-1
agent-loop privacy-scan --root "$PROJECT_ROOT"
agent-loop release-check --root "$PROJECT_ROOT"
agent-loop report "$RUN_ID" --root "$PROJECT_ROOT"
```

## Protocols

- `protocols/execution-protocol.md`: baseline worker/reviewer protocol.
- `protocols/karpathy-coding-guidelines.md`: caution-first coding guidelines.
- `docs/system-architecture.md`: system design and operating model.
- `docs/runtime-protocol.md`: task runtime loop.
- `docs/reference-insights.md`: design influences and tradeoffs.

## Privacy Notes

This repository is intended to be used as a reusable template. Avoid committing local run artifacts, machine-specific paths, private project names, tokens, or generated worker outputs. The default `.gitignore` excludes `.agent-runs/`, `.tasks/`, `.locks/`, `.agent-loop/`, caches, and bytecode.

## Status

This is an early but executable local framework. The safest current use is supervised automation: let Codex prepare bounded changes and evidence, then let a human approve commits and GitHub merges.
