from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import shlex
import subprocess
import time

from .dispatch import create_codex_command, create_worker_prompt
from .merge_gate import merge_preflight, preview_worktree
from .paths import LoopPaths
from .review import create_review
from .runs import create_run
from .state_machine import resume_run
from .tasks import activate_task, parse_task
from .worktree import find_worktree_path, start_worktree


def orchestrate(
    paths: LoopPaths,
    parallel: int,
    use_worktree: bool = False,
    run_codex: bool = False,
    watch: bool = False,
    timeout: float = 1800.0,
    run_command: str | None = None,
) -> list[str]:
    paths.ensure()
    messages: list[str] = []
    workers: list[dict] = []
    blocked_tasks: list[dict] = []
    selected_scopes: list[list[str]] = []

    if watch:
        workers.extend(load_existing_workers(paths))
        selected_scopes.extend(existing_worker_scopes(paths, workers))

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
        command_root = paths.root
        worktree_path = ""
        branch = ""
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
            "exit_code": "",
            "duration_seconds": "",
            "stdout_log": str(run_dir / "worker.stdout.log"),
            "stderr_log": str(run_dir / "worker.stderr.log"),
        }
        write_worker_evidence(run_dir, worker)
        workers.append(worker)
        messages.extend([f"started {run_dir.name} {agent_id}", f"created {prompt}", f"created {command}"])
        if run_codex or run_command:
            process = start_worker_process(run_dir, command_root, worker, run_command)
            worker["pid"] = process.pid
            worker["status"] = "running"
            worker["_process"] = process
            worker["_process_started"] = time.time()
            write_worker_evidence(run_dir, worker)

    if watch:
        wait_for_running_workers(workers, timeout)
        for worker in workers:
            run_dir = Path(worker["run_dir"])
            agent_id = worker["agent_id"]
            done = run_dir / "mailbox" / f"{agent_id}.done.md"
            blocked = run_dir / "mailbox" / f"{agent_id}.blocked.md"
            if blocked.exists():
                worker["status"] = "blocked"
                worker["finished_at"] = worker.get("finished_at") or now()
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
                    worker["finished_at"] = worker.get("finished_at") or now()
                except Exception as exc:
                    worker["status"] = "failed"
                    worker["finished_at"] = worker.get("finished_at") or now()
                    worker["failure"] = str(exc)
                write_worker_evidence(run_dir, worker)
                continue
            if str(worker.get("exit_code", "")) not in {"", "0"}:
                worker["status"] = "failed"
                worker["finished_at"] = worker.get("finished_at") or now()
                worker["failure"] = worker.get("failure") or f"worker exited {worker.get('exit_code')}"
                write_worker_evidence(run_dir, worker)

    write_orchestrate_outputs(paths, workers, blocked_tasks)
    if not messages and not workers and not blocked_tasks:
        messages.append("no pending tasks")
    return messages or ["orchestrate complete"]


def start_worker_process(run_dir: Path, cwd: Path, worker: dict, command: str | None) -> subprocess.Popen:
    stdout = open(run_dir / "worker.stdout.log", "w", encoding="utf-8")
    stderr = open(run_dir / "worker.stderr.log", "w", encoding="utf-8")
    env = os.environ.copy()
    env.update({"AGENT_ID": worker["agent_id"], "RUN_ID": worker["run_id"], "TASK_ID": worker["task_id"]})
    args = shlex.split(command) if command else ["sh", str(run_dir / f"{worker['agent_id']}.codex-command.sh")]
    process_cwd = run_dir if command else cwd
    return subprocess.Popen(args, cwd=process_cwd, stdout=stdout, stderr=stderr, env=env, text=True)


def existing_worker_scopes(paths: LoopPaths, workers: list[dict]) -> list[list[str]]:
    scopes: list[list[str]] = []
    for worker in workers:
        task_id = worker.get("task_id", "")
        for directory in [paths.active_dir, paths.done_dir]:
            for task_path in directory.glob("*.md"):
                task = parse_task(task_path)
                if task.task_id == task_id:
                    scopes.append(task.allowed_paths)
    return scopes


def wait_for_running_workers(workers: list[dict], timeout: float) -> None:
    deadline = time.time() + timeout
    running = [worker for worker in workers if worker.get("_process")]
    while running and time.time() < deadline:
        for worker in list(running):
            process = worker["_process"]
            exit_code = process.poll()
            if exit_code is not None:
                running.remove(worker)
                worker["exit_code"] = exit_code
                worker["duration_seconds"] = round(time.time() - float(worker.get("_process_started", time.time())), 3)
                worker["finished_at"] = now()
        if running:
            time.sleep(0.1)
    for worker in running:
        process = worker["_process"]
        process.kill()
        worker["exit_code"] = "timeout"
        worker["duration_seconds"] = round(time.time() - float(worker.get("_process_started", time.time())), 3)
        worker["finished_at"] = now()
        worker["status"] = "failed"
        worker["failure"] = "timeout"


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
    public = {k: v for k, v in worker.items() if not k.startswith("_") and k != "run_dir"}
    write_yaml(run_dir / "orchestrate-worker.yaml", public)


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
    lines.extend(f"  - {w['run_id']} {w['agent_id']} {w.get('failure', '')}" for w in failed) if failed else lines.append("  []")
    result.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report_lines = ["# Orchestrate Report", "", "## Started Workers"]
    report_lines.extend(
        f"- {w['agent_id']} `{w['run_id']}`: {w.get('status', '')} exit_code={w.get('exit_code', '')} log={Path(w.get('stdout_log', 'worker.stdout.log')).name}"
        for w in workers
    ) if workers else report_lines.append("- none")
    report_lines.extend(["", "## Blocked Tasks"])
    report_lines.extend(f"- {t['title']}: {t['reason']}" for t in blocked_tasks) if blocked_tasks else report_lines.append("- none")
    report_lines.extend(["", "## Review Ready"])
    report_lines.extend(f"- `{w['run_id']}` → `agent-loop report {w['run_id']} --root <project>`" for w in review_ready) if review_ready else report_lines.append("- none")
    report_lines.extend(["", "## Blocked Workers"])
    report_lines.extend(f"- `{w['run_id']}`" for w in blocked) if blocked else report_lines.append("- none")
    report_lines.extend(["", "## Failed Workers"])
    report_lines.extend(f"- {w['agent_id']} `{w['run_id']}`: {w.get('failure', '')}; stdout={Path(w.get('stdout_log', 'worker.stdout.log')).name}; stderr={Path(w.get('stderr_log', 'worker.stderr.log')).name}" for w in failed) if failed else report_lines.append("- none")
    report_lines.extend(["", "## Next Recommended Commands"])
    if review_ready:
        report_lines.extend(f"- `agent-loop report {w['run_id']} --root <project>`" for w in review_ready)
    if failed:
        report_lines.extend(f"- inspect `{w['run_id']}/worker.stderr.log`, then revise or split the task" for w in failed)
    if not review_ready and not failed:
        report_lines.append("- none")
    report_lines.extend(["", "## Human Gates", "- Review evidence before `review-accept`, `worktree-apply`, `accept`, or PR merge."])
    report.write_text("\n".join(report_lines) + "\n", encoding="utf-8")


def write_yaml(path: Path, data: dict) -> None:
    lines = []
    for key, value in data.items():
        lines.append(f"{key}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")
