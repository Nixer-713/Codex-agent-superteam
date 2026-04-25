from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import git_utils
from .paths import LoopPaths


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str
    action: str | None = None


def run_doctor(paths: LoopPaths) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(check_root(paths.root))
    findings.extend(check_git(paths.root))
    findings.extend(check_workspace(paths))
    findings.extend(check_tasks(paths))
    findings.extend(check_runs(paths))
    return findings


def check_root(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    if not root.exists():
        return [Finding("FAIL", "root.exists", f"root does not exist: {root}", "Create the directory or pass the correct --root path.")]
    if not root.is_dir():
        return [Finding("FAIL", "root.directory", f"root is not a directory: {root}", "Pass a project directory as --root.")]
    if os.access(root, os.W_OK):
        findings.append(Finding("OK", "root.writable", f"root is writable: {root}"))
    else:
        findings.append(Finding("FAIL", "root.writable", f"root is not writable: {root}", "Choose a writable project directory."))
    return findings


def check_git(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    repo = git_utils.git(root, "rev-parse", "--is-inside-work-tree")
    if repo.returncode == 0 and repo.stdout.strip() == "true":
        findings.append(Finding("OK", "git.repository", "Git repository detected."))
    else:
        findings.append(Finding("FAIL", "git.repository", "Not inside a Git repository.", "Run `git init` in the project root."))
        return findings

    user_name = git_utils.git(root, "config", "user.name")
    user_email = git_utils.git(root, "config", "user.email")
    if user_name.returncode == 0 and user_name.stdout.strip():
        findings.append(Finding("OK", "git.user_name", "Git user.name configured."))
    else:
        findings.append(Finding("WARN", "git.user_name", "Git user.name is not configured.", "Run `git config user.name '<name>'`."))
    if user_email.returncode == 0 and user_email.stdout.strip():
        findings.append(Finding("OK", "git.user_email", "Git user.email configured."))
    else:
        findings.append(Finding("WARN", "git.user_email", "Git user.email is not configured.", "Run `git config user.email '<email>'`."))
    return findings


def check_workspace(paths: LoopPaths) -> list[Finding]:
    required = [
        paths.config_file,
        paths.pending_dir,
        paths.active_dir,
        paths.done_dir,
        paths.runs_dir,
        paths.locks_dir,
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        return [
            Finding(
                "FAIL",
                "workspace.directories",
                "Agent Loop workspace is incomplete: " + ", ".join(str(path.relative_to(paths.root)) for path in missing),
                "Run `python3 -m agent_loop.cli init --root <project>` or `agent-loop init --root <project>`." ,
            )
        ]
    return [Finding("OK", "workspace.directories", "Agent Loop workspace directories exist.")]


def check_tasks(paths: LoopPaths) -> list[Finding]:
    if not paths.tasks_dir.exists():
        return []
    active = list(paths.active_dir.glob("*.md")) if paths.active_dir.exists() else []
    pending = list(paths.pending_dir.glob("*.md")) if paths.pending_dir.exists() else []
    done = list(paths.done_dir.glob("*.md")) if paths.done_dir.exists() else []
    findings = [Finding("OK", "tasks.counts", f"Tasks pending={len(pending)} active={len(active)} done={len(done)}.")]
    if len(active) > 1:
        findings.append(Finding("WARN", "tasks.active_many", f"Multiple active tasks found: {len(active)}.", "Finish or block active tasks before starting more."))
    return findings


def check_runs(paths: LoopPaths) -> list[Finding]:
    if not paths.runs_dir.exists():
        return []
    runs = sorted([path for path in paths.runs_dir.iterdir() if path.is_dir()])
    findings = [Finding("OK", "runs.count", f"Runs found: {len(runs)}.")]
    for run_dir in runs:
        status = run_dir / "status.yaml"
        task = run_dir / "input-task.md"
        if not status.exists():
            findings.append(Finding("WARN", "runs.status_missing", f"Missing status.yaml in {run_dir.name}."))
        if not task.exists():
            findings.append(Finding("WARN", "runs.task_missing", f"Missing input-task.md in {run_dir.name}."))
        scope = run_dir / "scope-check.yaml"
        if scope.exists() and "status: violation" in scope.read_text(encoding="utf-8"):
            findings.append(Finding("FAIL", "runs.scope_violation", f"Scope violation recorded in {run_dir.name}.", "Review scope-check.yaml before accepting."))
        if (run_dir / "worktrees.yaml").exists():
            findings.extend(check_worktree_evidence(run_dir))
        if status.exists() and is_review_ready_without_accept(status):
            findings.append(Finding("WARN", "runs.review_ready", f"Run {run_dir.name} is review_ready and awaits human accept."))
    return findings


def check_worktree_evidence(run_dir: Path) -> list[Finding]:
    required = [
        ("worktree-collect.yaml", "worktree-collect"),
        ("merge-preflight.yaml", "merge-preflight"),
        ("risk.yaml", "worktree-preview"),
        ("review-decision.yaml", "review-accept"),
        ("merge-result.yaml", "worktree-apply"),
    ]
    missing = [name for name, _ in required if not (run_dir / name).exists()]
    if not missing:
        return []
    next_command = next(command for name, command in required if name in missing)
    return [
        Finding(
            "WARN",
            "runs.worktree_evidence",
            f"Run {run_dir.name} is missing worktree evidence: " + ", ".join(missing),
            f"Run `{next_command} {run_dir.name} --root <project> --agent-id <agent>`.",
        )
    ]


def is_review_ready_without_accept(status_path: Path) -> bool:
    text = status_path.read_text(encoding="utf-8")
    return "phase: review_ready" in text and "status: accepted" not in text


def render_report(root: Path, findings: list[Finding]) -> str:
    counts = {"OK": 0, "WARN": 0, "FAIL": 0}
    lines = ["Codex Agent Loop Doctor", "", f"Root: {root}", ""]
    for finding in findings:
        counts[finding.level] += 1
        lines.append(f"[{finding.level}] {finding.code}: {finding.message}")
        if finding.action:
            lines.append(f"  action: {finding.action}")
    lines.extend(["", "Summary:", f"OK: {counts['OK']}", f"WARN: {counts['WARN']}", f"FAIL: {counts['FAIL']}"])
    return "\n".join(lines) + "\n"


def has_failures(findings: list[Finding]) -> bool:
    return any(finding.level == "FAIL" for finding in findings)
