from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LoopPaths:
    root: Path

    @property
    def config_dir(self) -> Path:
        return self.root / ".agent-loop"

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.yaml"

    @property
    def tasks_dir(self) -> Path:
        return self.root / ".tasks"

    @property
    def pending_dir(self) -> Path:
        return self.tasks_dir / "pending"

    @property
    def active_dir(self) -> Path:
        return self.tasks_dir / "active"

    @property
    def done_dir(self) -> Path:
        return self.tasks_dir / "done"

    @property
    def runs_dir(self) -> Path:
        return self.root / ".agent-runs"

    @property
    def locks_dir(self) -> Path:
        return self.root / ".locks"

    def ensure(self) -> None:
        for directory in [
            self.config_dir,
            self.pending_dir,
            self.active_dir,
            self.done_dir,
            self.runs_dir,
            self.locks_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)
        if not self.config_file.exists():
            self.config_file.write_text(
                "version: 1\nmode: local-cli-mvp\nautomation_goal: mostly_automatic_with_human_boundaries\n",
                encoding="utf-8",
            )


def resolve_paths(root: str | None) -> LoopPaths:
    if root == "/path/to/project":
        raise ValueError("placeholder root '/path/to/project' must be replaced with a real project directory")
    return LoopPaths(Path(root).expanduser().resolve() if root else Path.cwd().resolve())
