from __future__ import annotations

from pathlib import Path

CONFIG_TEMPLATE = """agents:
  default_agent_id: worker-1
  max_parallel: 2
validation:
  default_commands:
    - python3 -m pytest -q
risk:
  low_files: 3
  low_lines: 150
  medium_files: 8
  medium_lines: 500
git:
  branch_prefix: codex/
  require_clean_worktree: true
github:
  draft_pr: true
  require_ci_success: true
privacy:
  enabled: true
project:
  root: $PROJECT_ROOT
"""

ISSUE_TEMPLATE = """name: Codex Agent Task
description: Create a scoped task for Codex Agent Superteam
title: "[codex] "
body:
  - type: textarea
    id: task
    attributes:
      label: Task
      description: Describe the requested change for $PROJECT_ROOT.
  - type: input
    id: allowed
    attributes:
      label: Allowed paths
      placeholder: docs/**
  - type: input
    id: forbidden
    attributes:
      label: Forbidden paths
      placeholder: infra/**
  - type: input
    id: validation
    attributes:
      label: Validation command
      placeholder: python3 -m pytest -q
"""

PR_TEMPLATE = """## Codex Agent Superteam Evidence

- Run ID:
- Task ID:
- Changed files:
- Scope check:
- Risk:
- Validation:

## Human Gate

- [ ] I reviewed the GitHub diff.
- [ ] I reviewed local evidence from `$PROJECT_ROOT/.agent-runs/<run-id>/`.
- [ ] I approve merge.
"""


def template_init(root: Path, github_templates: bool = False) -> list[Path]:
    created: list[Path] = []
    config = root / ".agent-loop" / "config.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    if not config.exists():
        config.write_text(CONFIG_TEMPLATE, encoding="utf-8")
        created.append(config)
    if github_templates:
        issue = root / ".github" / "ISSUE_TEMPLATE" / "codex-task.yml"
        issue.parent.mkdir(parents=True, exist_ok=True)
        if not issue.exists():
            issue.write_text(ISSUE_TEMPLATE, encoding="utf-8")
            created.append(issue)
        pr = root / ".github" / "pull_request_template.md"
        if not pr.exists():
            pr.write_text(PR_TEMPLATE, encoding="utf-8")
            created.append(pr)
    return created
