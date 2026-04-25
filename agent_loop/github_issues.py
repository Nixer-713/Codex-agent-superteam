from __future__ import annotations

import json
from pathlib import Path

from .tasks import create_task
from .paths import LoopPaths


def import_issue(paths: LoopPaths, issue_number: str, from_file: Path | None = None) -> Path:
    if from_file:
        data = json.loads(from_file.read_text(encoding="utf-8"))
    else:
        raise RuntimeError("github-issue-import currently requires --from-file for deterministic import")
    body = data.get("body") or ""
    allowed: list[str] = []
    forbidden: list[str] = []
    validation: list[str] = []
    for line in body.splitlines():
        if line.startswith("allowed:"):
            allowed.append(line.split(":", 1)[1].strip())
        if line.startswith("forbidden:"):
            forbidden.append(line.split(":", 1)[1].strip())
        if line.startswith("validation:"):
            validation.append(line.split(":", 1)[1].strip())
    title = data.get("title") or f"GitHub issue {issue_number}"
    return create_task(paths, title, allowed, forbidden, validation)


def issue_comment_command(issue: str, run_id: str) -> str:
    return f"gh issue comment {issue} --body-file .agent-runs/{run_id}/github-issue-comment.md"


def write_issue_comment(paths: LoopPaths, run_id: str, issue: str) -> Path:
    run_dir = paths.runs_dir / run_id
    path = run_dir / "github-issue-comment.md"
    path.write_text(f"Codex Agent Superteam run `{run_id}` is ready for review evidence.\n", encoding="utf-8")
    return path


def write_pr_comments(run_dir: Path, from_file: Path | None = None) -> Path:
    output = run_dir / "pr-comments.md"
    if from_file and from_file.exists():
        output.write_text(from_file.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        output.write_text("# PR Comments\n\nNo PR comments imported.\n", encoding="utf-8")
    return output
