from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .paths import LoopPaths


@dataclass(frozen=True)
class TaskMeta:
    task_id: str
    title: str
    allowed_paths: list[str]
    forbidden_paths: list[str]
    validation_commands: list[str]
    path: Path


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
    return slug or "task"


def create_task(paths: LoopPaths, title: str, allowed: list[str], forbidden: list[str], validation: list[str]) -> Path:
    paths.ensure()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    task_id = f"task-{timestamp}-{slugify(title)}"
    task_path = paths.pending_dir / f"{task_id}.md"
    task_path.write_text(
        render_task(task_id, title, "pending", allowed, forbidden, validation),
        encoding="utf-8",
    )
    return task_path


def render_task(task_id: str, title: str, status: str, allowed: list[str], forbidden: list[str], validation: list[str]) -> str:
    return "\n".join(
        [
            "---",
            f"id: {task_id}",
            f"title: {title}",
            f"status: {status}",
            "allowed_paths:",
            *[f"  - {item}" for item in allowed],
            "forbidden_paths:",
            *[f"  - {item}" for item in forbidden],
            "validation_commands:",
            *[f"  - {item}" for item in validation],
            "---",
            "",
            "## Goal",
            title,
            "",
            "## Acceptance Criteria",
            "- [ ] Human or reviewer confirms task goal is met.",
            "",
            "## Non-Goals",
            "- Do not modify paths outside the declared scope.",
            "",
        ]
    )


def parse_task(path: Path) -> TaskMeta:
    text = path.read_text(encoding="utf-8")
    header = text.split("---", 2)[1] if text.startswith("---") else text
    data: dict[str, list[str] | str] = {}
    current_key: str | None = None
    for line in header.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            value = line[4:].strip()
            data.setdefault(current_key, [])
            assert isinstance(data[current_key], list)
            data[current_key].append(value)
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            current_key = key.strip()
            data[current_key] = value.strip() if value.strip() else []
    return TaskMeta(
        task_id=str(data.get("id", path.stem)),
        title=str(data.get("title", path.stem)),
        allowed_paths=list(data.get("allowed_paths", [])),
        forbidden_paths=list(data.get("forbidden_paths", [])),
        validation_commands=list(data.get("validation_commands", [])),
        path=path,
    )


def first_pending(paths: LoopPaths) -> Path | None:
    tasks = sorted(paths.pending_dir.glob("*.md"))
    return tasks[0] if tasks else None


def activate_task(paths: LoopPaths, task_path: Path) -> Path:
    target = paths.active_dir / task_path.name
    text = task_path.read_text(encoding="utf-8").replace("status: pending", "status: active", 1)
    target.write_text(text, encoding="utf-8")
    task_path.unlink()
    return target


def complete_active_task(paths: LoopPaths, task_id: str) -> Path:
    matches = list(paths.active_dir.glob(f"{task_id}.md"))
    if not matches:
        matches = [path for path in paths.active_dir.glob("*.md") if parse_task(path).task_id == task_id]
    if not matches:
        done_matches = list(paths.done_dir.glob(f"{task_id}.md"))
        if not done_matches:
            done_matches = [path for path in paths.done_dir.glob("*.md") if parse_task(path).task_id == task_id]
        if done_matches:
            return done_matches[0]
        raise FileNotFoundError(f"active task not found: {task_id}")
    source = matches[0]
    target = paths.done_dir / source.name
    text = source.read_text(encoding="utf-8").replace("status: active", "status: done", 1)
    target.write_text(text, encoding="utf-8")
    source.unlink()
    return target
