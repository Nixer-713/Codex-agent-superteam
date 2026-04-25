from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .dispatch import create_codex_command, create_worker_prompt


def codex_exec_args(root: Path, prompt_path: Path, output_path: Path) -> list[str]:
    return [
        "codex",
        "exec",
        "--cd",
        str(root),
        "--sandbox",
        "workspace-write",
        "--output-last-message",
        str(output_path),
        "-",
    ]


def shell_command(args: list[str], prompt_path: Path) -> str:
    return " ".join(shlex.quote(arg) for arg in args) + " < " + shlex.quote(str(prompt_path))


def run_codex_worker(root: Path, run_dir: Path, agent_id: str, dry_run: bool, timeout_seconds: int) -> tuple[int, str]:
    prompt_path = run_dir / f"{agent_id}.prompt.md"
    if not prompt_path.exists():
        create_worker_prompt(run_dir, agent_id)
    create_codex_command(run_dir, root, agent_id)
    output_path = run_dir / f"{agent_id}.codex-output.txt"
    args = codex_exec_args(root, prompt_path, output_path)
    command_text = shell_command(args, prompt_path)
    if dry_run:
        return 0, command_text

    with prompt_path.open("r", encoding="utf-8") as prompt_file:
        completed = subprocess.run(
            args,
            stdin=prompt_file,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
    log_path = run_dir / f"{agent_id}.codex-run.log"
    log_path.write_text(
        "COMMAND\n" + command_text + "\n\nSTDOUT\n" + completed.stdout + "\n\nSTDERR\n" + completed.stderr,
        encoding="utf-8",
    )
    return completed.returncode, str(log_path)
