from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from .advance import ScopeViolation, advance_run
from .worktree import collect_worker_signal, find_worktree_path


class WatchTimeout(RuntimeError):
    pass


class WorkerBlocked(RuntimeError):
    pass


def write_blocked(run_dir: Path, agent_id: str, reason: str) -> Path:
    mailbox = run_dir / "mailbox"
    mailbox.mkdir(exist_ok=True)
    blocked_path = mailbox / f"{agent_id}.blocked.md"
    now = datetime.now().isoformat(timespec="seconds")
    blocked_path.write_text(
        f"""---
agent_id: {agent_id}
status: blocked
blocked_at: {now}
---

# Worker Blocked

{reason}
""",
        encoding="utf-8",
    )
    append_agent_status(run_dir / "status.yaml", agent_id, "blocked")
    return blocked_path


def watch_run(root: Path, run_dir: Path, agent_id: str, timeout_seconds: float, poll_seconds: float) -> str:
    deadline = time.monotonic() + timeout_seconds
    first_check = True
    while first_check or time.monotonic() <= deadline:
        first_check = False
        done_path = run_dir / "mailbox" / f"{agent_id}.done.md"
        blocked_path = run_dir / "mailbox" / f"{agent_id}.blocked.md"
        if not done_path.exists() and not blocked_path.exists():
            collect_worker_signal(run_dir, agent_id)
        if blocked_path.exists():
            raise WorkerBlocked(f"blocked signal found: {blocked_path}")
        if done_path.exists():
            diff_root = find_worktree_path(run_dir, agent_id) or root
            advance_run(diff_root, run_dir, agent_id)
            return "review_ready"
        if timeout_seconds <= 0:
            break
        time.sleep(max(poll_seconds, 0.05))
    raise WatchTimeout(f"timeout waiting for done signal from {agent_id}")


def append_agent_status(status_path: Path, agent_id: str, status: str) -> None:
    text = status_path.read_text(encoding="utf-8") if status_path.exists() else ""
    if f"{agent_id}: {status}" not in text:
        text = text.rstrip() + f"\nagents:\n" if "agents:" not in text else text.rstrip() + "\n"
        text += f"  {agent_id}: {status}\n"
    status_path.write_text(text, encoding="utf-8")
