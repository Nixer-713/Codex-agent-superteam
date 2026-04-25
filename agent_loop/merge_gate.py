from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from . import git_utils
from .review import create_review
from .scope_guard import check_scope, write_scope_report
from .tasks import parse_task
from .worktree import collect_worker_signal, find_worktree_path


class MergeGateError(RuntimeError):
    pass


def find_worktree_branch(run_dir: Path, agent_id: str) -> str:
    record = run_dir / "worktrees.yaml"
    if not record.exists():
        return ""
    lines = record.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip() == f"- agent_id: {agent_id}":
            for following in lines[index + 1 : index + 4]:
                stripped = following.strip()
                if stripped.startswith("branch:"):
                    return stripped.split(":", 1)[1].strip()
    return ""


def changed_files(root: Path) -> list[str]:
    return git_utils.diff_name_only(root)


def collect_worktree(root: Path, run_dir: Path, agent_id: str) -> None:
    worktree = require_worktree(run_dir, agent_id)
    signal = collect_worker_signal(run_dir, agent_id)
    files = changed_files(worktree)
    branch = find_worktree_branch(run_dir, agent_id)
    write_lines(run_dir / "changed-files.txt", files)
    (run_dir / "diff-stat.txt").write_text(git_utils.diff_stat(worktree), encoding="utf-8")
    (run_dir / "diff.patch").write_text(git_utils.full_diff(worktree), encoding="utf-8")
    write_yaml(
        run_dir / "worktree-collect.yaml",
        {
            "status": "ok",
            "agent_id": agent_id,
            "source_worktree": str(worktree),
            "source_branch": branch,
            "mailbox_signal": str(signal) if signal else "missing",
            "changed_files": files,
        },
    )


def merge_preflight(root: Path, run_dir: Path, agent_id: str) -> bool:
    worktree = find_worktree_path(run_dir, agent_id)
    branch = find_worktree_branch(run_dir, agent_id)
    collect_worker_signal(run_dir, agent_id)
    done = run_dir / "mailbox" / f"{agent_id}.done.md"
    files = changed_files(worktree) if worktree and worktree.exists() else []
    main_status = git_utils.status_short(root).splitlines()
    conflicts = [file for file in files if has_main_conflict(root, file)]
    failures: list[str] = []
    if not worktree or not worktree.exists():
        failures.append("worktree: missing")
    if not branch:
        failures.append("branch: missing")
    if not done.exists():
        failures.append("done_signal: missing")
    if conflicts:
        failures.append("conflicts: present")
    status = "ok" if not failures else "fail"
    report = {
        "status": status,
        "agent_id": agent_id,
        "source_worktree": str(worktree) if worktree else "missing",
        "source_branch": branch or "missing",
        "done_signal": "present" if done.exists() else "missing",
        "conflicts": conflicts,
        "main_status": main_status,
        "failures": failures,
    }
    write_yaml(run_dir / "merge-preflight.yaml", report)
    return status == "ok"


def preview_worktree(root: Path, run_dir: Path, agent_id: str) -> bool:
    collect_worktree(root, run_dir, agent_id)
    worktree = require_worktree(run_dir, agent_id)
    task = parse_task(run_dir / "input-task.md")
    files = changed_files(worktree)
    scope = check_scope(task, files)
    write_scope_report(run_dir / "scope-check.yaml", scope)
    write_risk(run_dir / "risk.yaml", files, git_utils.full_diff(worktree))
    write_validation(run_dir / "validation.yaml", task.validation_commands)
    create_review(run_dir)
    append_review_decision(run_dir / "review.md", "needs_human_decision")
    return scope.status == "ok"


def review_accept(run_dir: Path, agent_id: str) -> None:
    required = ["scope-check.yaml", "risk.yaml", "merge-preflight.yaml", "review.md"]
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise MergeGateError("missing evidence for review-accept: " + ", ".join(missing))
    if "status: ok" not in (run_dir / "scope-check.yaml").read_text(encoding="utf-8"):
        raise MergeGateError("scope-check is not ok")
    if "status: ok" not in (run_dir / "merge-preflight.yaml").read_text(encoding="utf-8"):
        raise MergeGateError("merge-preflight is not ok")
    write_yaml(
        run_dir / "review-decision.yaml",
        {
            "decision": "accept",
            "accepted_by": "human",
            "accepted_at": datetime.now().isoformat(timespec="seconds"),
            "agent_id": agent_id,
            "evidence": required,
        },
    )


def apply_worktree(root: Path, run_dir: Path, agent_id: str) -> None:
    require_apply_evidence(run_dir)
    if "risk: high" in (run_dir / "risk.yaml").read_text(encoding="utf-8"):
        raise MergeGateError("risk is high; manual merge required")
    if not merge_preflight(root, run_dir, agent_id):
        raise MergeGateError("merge-preflight failed")
    worktree = require_worktree(run_dir, agent_id)
    expected = read_lines(run_dir / "changed-files.txt")
    task = parse_task(run_dir / "input-task.md")
    scope = check_scope(task, expected)
    if scope.status != "ok":
        raise MergeGateError("scope-check is not ok")
    for file in expected:
        copy_allowed_file(worktree, root, file)
    actual = changed_files(root)
    matching_actual = [file for file in actual if file in expected]
    match = sorted(expected) == sorted(matching_actual)
    (run_dir / "post-apply-diff.patch").write_text(git_utils.full_diff(root), encoding="utf-8")
    write_yaml(
        run_dir / "merge-result.yaml",
        {
            "status": "ok" if match else "fail",
            "agent_id": agent_id,
            "expected_files": expected,
            "actual_files": matching_actual,
            "match": "true" if match else "false",
        },
    )
    if not match:
        raise MergeGateError("applied files do not match preview")
    append_phase(run_dir / "status.yaml", "merge_ready")


def require_worktree(run_dir: Path, agent_id: str) -> Path:
    worktree = find_worktree_path(run_dir, agent_id)
    if not worktree or not worktree.exists():
        raise MergeGateError(f"worktree missing for {agent_id}")
    return worktree


def has_main_conflict(root: Path, file: str) -> bool:
    status = git_utils.status_short(root).splitlines()
    return any(line[3:] == file or line.endswith(" " + file) for line in status)


def require_apply_evidence(run_dir: Path) -> None:
    required = ["scope-check.yaml", "risk.yaml", "merge-preflight.yaml", "review-decision.yaml", "changed-files.txt"]
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise MergeGateError("missing evidence: " + ", ".join(missing))
    if "decision: accept" not in (run_dir / "review-decision.yaml").read_text(encoding="utf-8"):
        raise MergeGateError("review-decision is not accept")


def copy_allowed_file(worktree: Path, root: Path, file: str) -> None:
    if file.startswith(("mailbox/", ".agent-loop/", ".agent-runs/", ".tasks/", ".locks/")):
        raise MergeGateError(f"refusing to apply runtime file: {file}")
    source = worktree / file
    target = root / file
    if not source.exists() or not source.is_file():
        raise MergeGateError(f"only ordinary file additions/modifications are supported: {file}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def write_risk(path: Path, files: list[str], diff: str, thresholds: dict | None = None) -> None:
    thresholds = thresholds or {}
    low_files = int(thresholds.get("low_files", 3))
    low_lines = int(thresholds.get("low_lines", 150))
    medium_files = int(thresholds.get("medium_files", 8))
    medium_lines = int(thresholds.get("medium_lines", 500))
    added = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    deleted = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
    changed = added + deleted
    if len(files) <= low_files and changed <= low_lines:
        risk = "low"
    elif len(files) <= medium_files and changed <= medium_lines:
        risk = "medium"
    else:
        risk = "high"
    write_yaml(path, {"files_changed": len(files), "lines_added": added, "lines_deleted": deleted, "risk": risk})


def write_validation(path: Path, commands: list[str]) -> None:
    if not commands:
        write_yaml(path, {"status": "skipped", "reason": "no validation command declared"})
    else:
        write_yaml(path, {"status": "skipped", "reason": "validation execution not implemented in merge preview", "commands": commands})


def append_review_decision(path: Path, decision: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else "# Review Report\n"
    if "decision:" not in text:
        text += f"\n```yaml\ndecision: {decision}\n```\n"
    path.write_text(text, encoding="utf-8")


def append_phase(status_path: Path, phase: str) -> None:
    text = status_path.read_text(encoding="utf-8") if status_path.exists() else ""
    if f"phase: {phase}" not in text:
        text = text.rstrip() + f"\nphase: {phase}\n"
    status_path.write_text(text, encoding="utf-8")


def read_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_yaml(path: Path, data: dict) -> None:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            if value:
                lines.extend(f"  - {item}" for item in value)
            continue
        lines.append(f"{key}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def is_worktree_run(run_dir: Path) -> bool:
    return (run_dir / "worktrees.yaml").exists()


def is_merge_ready(run_dir: Path) -> bool:
    status = (run_dir / "status.yaml").read_text(encoding="utf-8") if (run_dir / "status.yaml").exists() else ""
    result = (run_dir / "merge-result.yaml").read_text(encoding="utf-8") if (run_dir / "merge-result.yaml").exists() else ""
    return "phase: merge_ready" in status and "match: true" in result
