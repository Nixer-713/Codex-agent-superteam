from __future__ import annotations

from pathlib import Path

from . import git_utils
from .review import create_review
from .scope_guard import check_scope, write_scope_report
from .tasks import parse_task


class MissingDoneSignal(RuntimeError):
    pass


def advance_run(root: Path, run_dir: Path, agent_id: str) -> None:
    done_path = run_dir / "mailbox" / f"{agent_id}.done.md"
    if not done_path.exists():
        raise MissingDoneSignal(f"missing done signal: {done_path}")

    changed = git_utils.diff_name_only(root)
    (run_dir / "changed-files.txt").write_text("\n".join(changed) + ("\n" if changed else ""), encoding="utf-8")
    (run_dir / "diff-stat.txt").write_text(git_utils.diff_stat(root), encoding="utf-8")
    (run_dir / "diff.patch").write_text(git_utils.full_diff(root), encoding="utf-8")

    task = parse_task(run_dir / "input-task.md")
    scope_result = check_scope(task, changed)
    write_scope_report(run_dir / "scope-check.yaml", scope_result)
    create_review(run_dir)
    append_status(run_dir / "status.yaml", "review_ready")

    if scope_result.status != "ok":
        raise ScopeViolation("scope violation")


class ScopeViolation(RuntimeError):
    pass


def append_status(status_path: Path, marker: str) -> None:
    text = status_path.read_text(encoding="utf-8") if status_path.exists() else ""
    if marker not in text:
        text = text.rstrip() + f"\nphase: {marker}\n"
    status_path.write_text(text, encoding="utf-8")
