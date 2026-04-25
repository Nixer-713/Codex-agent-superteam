from __future__ import annotations

from pathlib import Path

from .dispatch import create_worker_prompt
from .paths import LoopPaths
from .runs import create_run
from .tasks import activate_task, first_pending, parse_task


def orchestrate(paths: LoopPaths, parallel: int) -> list[str]:
    paths.ensure()
    messages: list[str] = []
    for _ in range(parallel):
        pending = first_pending(paths)
        if not pending:
            break
        active = activate_task(paths, pending)
        run_dir = create_run(paths, parse_task(active))
        prompt = create_worker_prompt(run_dir, "worker-1")
        messages.append(f"started {run_dir.name}")
        messages.append(f"created {prompt}")
    if not messages:
        messages.append("no pending tasks")
    return messages
