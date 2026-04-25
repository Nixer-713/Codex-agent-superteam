from __future__ import annotations

from pathlib import Path

from . import git_utils
from .advance import ScopeViolation
from .codex_runner import run_codex_worker
from .dispatch import create_codex_command, create_worker_prompt
from .doctor import has_failures, run_doctor
from .paths import LoopPaths
from .runs import create_run
from .tasks import activate_task, first_pending, parse_task
from .watch import WatchTimeout, WorkerBlocked, watch_run
from .worktree import start_worktree


class AutoNextError(RuntimeError):
    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


def auto_next(
    paths: LoopPaths,
    agent_id: str,
    codex_command: bool,
    run_codex: bool,
    dry_run: bool,
    watch: bool,
    watch_timeout: float,
    use_worktree: bool = False,
    worktree_path: Path | None = None,
) -> tuple[int, list[str]]:
    messages: list[str] = []
    git_utils.require_git_repository(paths.root)
    findings = run_doctor(paths)
    if has_failures(findings):
        raise AutoNextError("doctor reported failures; fix them before auto-next", 1)
    messages.append("doctor ok")

    pending = first_pending(paths)
    if not pending:
        raise AutoNextError("no pending tasks", 1)
    active_path = activate_task(paths, pending)
    run_dir = create_run(paths, parse_task(active_path))
    messages.append(f"started {run_dir.name}")

    worker_root = paths.root
    if use_worktree:
        worker_root, branch = start_worktree(paths.root, run_dir, agent_id, worktree_path)
        messages.append(f"worktree {worker_root}")
        messages.append(f"branch {branch}")

    prompt_path = create_worker_prompt(run_dir, agent_id)
    messages.append(f"dispatched {prompt_path}")
    if codex_command or run_codex:
        command_path = create_codex_command(run_dir, worker_root, agent_id)
        messages.append(f"codex_command {command_path}")

    if run_codex:
        returncode, output = run_codex_worker(worker_root, run_dir, agent_id, dry_run, 1800)
        messages.append(f"run_codex {output}")
        if returncode != 0:
            return returncode, messages

    if watch:
        try:
            result = watch_run(paths.root, run_dir, agent_id, watch_timeout, 2.0)
            messages.append(f"{result} {run_dir.name}")
        except WorkerBlocked as exc:
            raise AutoNextError(str(exc), 4) from exc
        except WatchTimeout as exc:
            raise AutoNextError(str(exc), 3) from exc
        except ScopeViolation as exc:
            raise AutoNextError(str(exc), 2) from exc

    return 0, messages
