from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from . import git_utils
from .paths import LoopPaths
from .tasks import TaskMeta


def create_run(paths: LoopPaths, task: TaskMeta) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"run-{timestamp}-{task.task_id}"
    run_dir = paths.runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(task.path, run_dir / "input-task.md")
    (run_dir / "before-head.txt").write_text(git_utils.current_head(paths.root) + "\n", encoding="utf-8")
    (run_dir / "before-status.txt").write_text(git_utils.status_short(paths.root), encoding="utf-8")
    (run_dir / "context-pack.md").write_text(render_context_pack(task), encoding="utf-8")
    (run_dir / "worker-brief.md").write_text(render_worker_brief(task, run_id), encoding="utf-8")
    (run_dir / "status.yaml").write_text(
        f"run_id: {run_id}\ntask_id: {task.task_id}\nstatus: running\nattempts: 0\n",
        encoding="utf-8",
    )
    (run_dir / "mailbox").mkdir()
    return run_dir


def get_run(paths: LoopPaths, run_id: str) -> Path:
    run_dir = paths.runs_dir / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run not found: {run_id}")
    return run_dir


def run_task_id(run_dir: Path) -> str:
    for line in (run_dir / "status.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("task_id:"):
            return line.split(":", 1)[1].strip()
    raise ValueError("status.yaml missing task_id")


def render_context_pack(task: TaskMeta) -> str:
    return f"""# Context Pack

## Task

- ID: {task.task_id}
- Title: {task.title}

## Scope

Allowed paths:
{format_list(task.allowed_paths)}

Forbidden paths:
{format_list(task.forbidden_paths)}

## Validation Commands

{format_list(task.validation_commands)}

## Token Policy

Read this context first. Only open full source files or full diffs when needed. Keep output summaries compact and write detailed evidence to files.
"""


def render_worker_brief(task: TaskMeta, run_id: str) -> str:
    return f"""# Worker Brief

## Run ID

{run_id}

## Goal

{task.title}

## Owned / Allowed Paths

{format_list(task.allowed_paths)}

## Forbidden Paths

{format_list(task.forbidden_paths)}

## Completion Signal

Before finishing, write a concise summary and completion message under this run's `mailbox/` directory. Do not commit unless the main agent explicitly asks.

## Stop Conditions

Stop and mark blocked if required changes exceed allowed paths, require public API/schema changes, or validation cannot run for unknown reasons.
"""


def format_list(items: list[str]) -> str:
    if not items:
        return "- <none declared>"
    return "\n".join(f"- {item}" for item in items)
