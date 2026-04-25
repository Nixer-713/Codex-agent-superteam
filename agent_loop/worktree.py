from __future__ import annotations

from pathlib import Path
import shutil

from . import git_utils
from .runs import run_task_id


def safe_branch_part(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "-" for char in value).strip("-")


def start_worktree(root: Path, run_dir: Path, agent_id: str, path: Path | None) -> tuple[Path, str]:
    task_id = run_task_id(run_dir)
    branch = f"codex/{safe_branch_part(task_id)}-{safe_branch_part(agent_id)}"
    worktree_path = path or root.parent / f"{root.name}-{safe_branch_part(task_id)}-{safe_branch_part(agent_id)}"
    result = git_utils.git(root, "worktree", "add", "-b", branch, str(worktree_path))
    if result.returncode != 0:
        existing = git_utils.git(root, "branch", "--list", branch)
        if existing.returncode == 0 and existing.stdout.strip() and worktree_path.exists():
            pass
        else:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    record_worktree(run_dir, agent_id, branch, worktree_path)
    return worktree_path, branch


def record_worktree(run_dir: Path, agent_id: str, branch: str, worktree_path: Path) -> None:
    record = run_dir / "worktrees.yaml"
    existing = record.read_text(encoding="utf-8") if record.exists() else "worktrees:\n"
    existing += f"  - agent_id: {agent_id}\n    branch: {branch}\n    path: {worktree_path}\n"
    record.write_text(existing, encoding="utf-8")


def find_worktree_path(run_dir: Path, agent_id: str) -> Path | None:
    record = run_dir / "worktrees.yaml"
    if not record.exists():
        return None
    lines = record.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip() == f"- agent_id: {agent_id}":
            for following in lines[index + 1 : index + 4]:
                stripped = following.strip()
                if stripped.startswith("path:"):
                    return Path(stripped.split(":", 1)[1].strip())
    return None


def collect_worker_signal(run_dir: Path, agent_id: str) -> Path | None:
    worktree_path = find_worktree_path(run_dir, agent_id)
    if not worktree_path:
        return None
    mailbox = run_dir / "mailbox"
    mailbox.mkdir(exist_ok=True)
    for suffix in ["done", "blocked"]:
        source = worktree_path / "mailbox" / f"{agent_id}.{suffix}.md"
        if source.exists():
            target = mailbox / source.name
            shutil.copyfile(source, target)
            return target
    return None
