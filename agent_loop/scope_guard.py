from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

from .tasks import TaskMeta


@dataclass(frozen=True)
class ScopeResult:
    status: str
    violations: list[str]
    changed_files: list[str]


def check_scope(task: TaskMeta, changed_files: list[str]) -> ScopeResult:
    violations: list[str] = []
    for changed in changed_files:
        if any(fnmatch.fnmatch(changed, pattern) for pattern in task.forbidden_paths):
            violations.append(changed)
            continue
        if task.allowed_paths and not any(fnmatch.fnmatch(changed, pattern) for pattern in task.allowed_paths):
            violations.append(changed)
    return ScopeResult("violation" if violations else "ok", violations, changed_files)


def write_scope_report(path: Path, result: ScopeResult) -> None:
    lines = ["status: " + result.status, "violations:"]
    lines.extend(f"  - {item}" for item in result.violations)
    lines.append("changed_files:")
    lines.extend(f"  - {item}" for item in result.changed_files)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
