from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import git_utils
from .dispatch import create_codex_command, create_worker_prompt
from .merge_gate import merge_preflight, preview_worktree
from .paths import LoopPaths
from .review import create_review
from .runs import create_run
from .state_machine import resume_run
from .tasks import activate_task, parse_task
from .worktree import find_worktree_path, start_worktree


def orchestrate(paths: LoopPaths, parallel: int, use_worktree: bool = False, run_codex: bool = False, watch: bool = False, timeout: float = 1800.0) -> list[str]:
    paths.ensure()
    messages: list[str] = []
    workers: list[dict] = []
    blocked_tasks: list[dict] = []
    selected_scopes: list[list[str]] = []

    if watch:
        workers.extend(load_existing_workers(paths))
    else:
        pending = sorted(paths.pending_dir.glob("*.md"))[: max(parallel * 2, parallel)]
        for task_path in pending:
            if len(workers) >= parallel:
                break
            task = parse_task(task_path)
            if conflicts_with_existing(task.allowed_paths, selected_scopes):
                blocked_tasks.append({"task_id": task.task_id, "title": task.title, "reason": "allowed_paths conflict"})
                continue
            selected_scopes.append(task.allowed_paths)
            active = activate_task(paths, task_path)
            task = parse_task(active)
            run_dir = create_run(paths, task)
            agent_id = f"worker-{len(workers) + 1}"
            worktree_path = ""
            branch = ""
            command_root = paths.root
            if use_worktree:
                default_path = paths.root.parent / f"{paths.root.name}-agent-loop" / f"{run_dir.name}-{agent_id}"
                worktree, branch = start_worktree(paths.root, run_dir, agent_id, default_path)
                worktree_path = str(worktree)
                command_root = worktree
            prompt = create_worker_prompt(run_dir, agent_id)
            command = create_codex_command(run_dir, command_root, agent_id)
            worker = {
                "agent_id": agent_id,
                "run_id": run_dir.name,
                "task_id": task.task_id,
                "title": task.title,
                "run_dir": str(run_dir),
                "worktree_path": worktree_path,
                "branch": branch,
                "status": "started",
                "started_at": now(),
                "finished_at": "",
            }
            write_worker_evidence(run_dir, worker)
            workers.append(worker)
            messages.append(f"started {run_dir.name} {agent_id}")
            messages.append(f"created {prompt}")
            messages.append(f"created {command}")
            if run_codex:
                worker["status"] = "failed"
                worker["finished_at"] = now()
                worker["failure"] = "run-codex execution is intentionally not launched by orchestrate v0.3 in tests; use generated command or run-codex"
                write_worker_evidence(run_dir, worker)

    if watch:
        for worker in workers:
            run_dir = Path(worker["run_dir"])
            agent_id = worker["agent_id"]
            done = run_dir / "mailbox" / f"{agent_id}.done.md"
            blocked = run_dir / "mailbox" / f"{agent_id}.blocked.md"
            if blocked.exists():
                worker["status"] = "blocked"
                worker["finished_at"] = now()
                write_worker_evidence(run_dir, worker)
                continue
            if done.exists():
                try:
                    if (run_dir / "worktrees.yaml").exists() and find_worktree_path(run_dir, agent_id):
                        merge_preflight(paths.root, run_dir, agent_id)
                        preview_worktree(paths.root, run_dir, agent_id)
                    else:
                        resume_run(paths.root, run_dir)
                    if not (run_dir / "review.md").exists():
                        create_review(run_dir)
                    worker["status"] = "review_ready"
                    worker["finished_at"] = now()
                except Exception as exc:  # evidence, don't abort other workers
                    worker["status"] = "failed"
                    worker["finished_at"] = now()
                    worker["failure"] = str(exc)
                write_worker_evidence(run_dir, worker)

    write_orchestrate_outputs(paths, workers, blocked_tasks)
    if not messages and not workers and not blocked_tasks:
        messages.append("no pending tasks")
    return messages or ["orchestrate complete"]


def load_existing_workers(paths: LoopPaths) -> list[dict]:
    workers: list[dict] = []
    if not paths.runs_dir.exists():
        return workers
    for evidence in sorted(paths.runs_dir.glob("*/orchestrate-worker.yaml")):
        worker = parse_worker_evidence(evidence)
        worker["run_dir"] = str(evidence.parent)
        workers.append(worker)
    return workers


def conflicts_with_existing(paths: list[str], selected: list[list[str]]) -> bool:
    return any(paths_conflict(paths, existing) for existing in selected)


def paths_conflict(left: list[str], right: list[str]) -> bool:
    if not left or not right:
        return True
    return any(patterns_overlap(a, b) for a in left for b in right)


def patterns_overlap(left: str, right: str) -> bool:
    left_base = normalize_pattern(left)
    right_base = normalize_pattern(right)
    return left_base == right_base or left_base.startswith(right_base + "/") or right_base.startswith(left_base + "/")


def normalize_pattern(pattern: str) -> str:
    return pattern.replace("/**", "").rstrip("/")


def write_worker_evidence(run_dir: Path, worker: dict) -> None:
    write_yaml(run_dir / "orchestrate-worker.yaml", {k: v for k, v in worker.items() if k != "run_dir"})


def parse_worker_evidence(path: Path) -> dict:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line and not line.startswith("  "):
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


def write_orchestrate_outputs(paths: LoopPaths, workers: list[dict], blocked_tasks: list[dict]) -> None:
    result = paths.config_dir / "orchestrate-result.yaml"
    report = paths.config_dir / "orchestrate-report.md"
    review_ready = [w for w in workers if w.get("status") == "review_ready"]
    failed = [w for w in workers if w.get("status") == "failed"]
    blocked = [w for w in workers if w.get("status") == "blocked"]
    lines = ["status: ok", "started_workers:"]
    lines.extend(f"  - {w['run_id']} {w['agent_id']} {w.get('status', '')}" for w in workers) if workers else lines.append("  []")
    lines.append("blocked_tasks:")
    if blocked_tasks:
        for task in blocked_tasks:
            lines.append(f"  - {task['task_id']}: {task['title']} ({task['reason']})")
    else:
        lines.append("  []")
    lines.append("review_ready_runs:")
    lines.extend(f"  - {w['run_id']}" for w in review_ready) if review_ready else lines.append("  []")
    lines.append("failed_workers:")
    lines.extend(f"  - {w['run_id']} {w.get('failure', '')}" for w in failed) if failed else lines.append("  []")
    result.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report_lines = ["# Orchestrate Report", "", "## Started Workers"]
    report_lines.extend(f"- {w['agent_id']} `{w['run_id']}`: {w.get('status', '')}" for w in workers) if workers else report_lines.append("- none")
    report_lines.extend(["", "## Blocked Tasks"])
    report_lines.extend(f"- {t['title']}: {t['reason']}" for t in blocked_tasks) if blocked_tasks else report_lines.append("- none")
    report_lines.extend(["", "## Review Ready"])
    report_lines.extend(f"- `{w['run_id']}` → `agent-loop report {w['run_id']} --root <project>`" for w in review_ready) if review_ready else report_lines.append("- none")
    report_lines.extend(["", "## Blocked Workers"])
    report_lines.extend(f"- `{w['run_id']}`" for w in blocked) if blocked else report_lines.append("- none")
    report_lines.extend(["", "## Failed Workers"])
    report_lines.extend(f"- `{w['run_id']}`: {w.get('failure', '')}" for w in failed) if failed else report_lines.append("- none")
    report_lines.extend(["", "## Human Gates", "- Review evidence before `review-accept`, `worktree-apply`, `accept`, or PR merge."])
    report.write_text("\n".join(report_lines) + "\n", encoding="utf-8")


def write_yaml(path: Path, data: dict) -> None:
    lines = []
    for key, value in data.items():
        lines.append(f"{key}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")
