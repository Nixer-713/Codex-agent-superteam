from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shlex

from .tasks import parse_task


def create_worker_prompt(run_dir: Path, agent_id: str) -> Path:
    task = parse_task(run_dir / "input-task.md")
    prompt_path = run_dir / f"{agent_id}.prompt.md"
    prompt_path.write_text(
        f"""# Codex Worker Prompt

You are a bounded Codex worker. Complete only the task described here. Do not expand scope, do not commit, and do not modify files outside the allowed paths.

## Bottom Execution Protocol

Follow the project baseline protocols before editing:

- `protocols/execution-protocol.md`
- `protocols/karpathy-coding-guidelines.md` / Karpathy Coding Guidelines

Operational summary: think before coding, state assumptions when unclear, prefer the smallest working patch, make surgical changes only, avoid speculative abstractions, and verify behavior before claiming completion.

## Agent ID

{agent_id}

## Task

- ID: {task.task_id}
- Title: {task.title}

## Allowed Paths

{format_list(task.allowed_paths)}

## Forbidden Paths

{format_list(task.forbidden_paths)}

## Validation Commands

{format_list(task.validation_commands)}

## Required Workflow

1. Read `context-pack.md` and `worker-brief.md` in this run directory.
2. Make the smallest code/documentation change that satisfies the task.
3. Do not touch forbidden paths.
4. If the task requires forbidden paths or unclear architecture decisions, stop and write `mailbox/{agent_id}.blocked.md`.
5. When finished, run the relevant validation command if practical.
6. Write `mailbox/{agent_id}.done.md` with changed files, validation result, and a concise summary.
7. Do not run `git commit`.

## Completion File Format

Write this file before ending:

```text
mailbox/{agent_id}.done.md
```

Suggested content:

```yaml
agent_id: {agent_id}
status: done
result: success
changed_files:
  - path/to/file
validation:
  - command: <command or not-run>
    result: <passed | failed | skipped>
summary: <brief summary>
```

## Main-Agent Contract

The main agent will inspect `mailbox/{agent_id}.done.md`, `git diff --name-only`, `scope-check`, and review artifacts. Your chat message is not the source of truth; files and Git diff are.
""",
        encoding="utf-8",
    )
    return prompt_path


def create_codex_command(run_dir: Path, root: Path, agent_id: str) -> Path:
    prompt_path = run_dir / f"{agent_id}.prompt.md"
    if not prompt_path.exists():
        create_worker_prompt(run_dir, agent_id)
    command_path = run_dir / f"{agent_id}.codex-command.sh"
    command = [
        "codex",
        "exec",
        "--cd",
        str(root),
        "--sandbox",
        "workspace-write",
        "-",
        "<",
        str(prompt_path),
    ]
    command_path.write_text(" ".join(shlex.quote(part) if part != "<" else part for part in command) + "\n", encoding="utf-8")
    command_path.chmod(0o755)
    return command_path


def write_completion(run_dir: Path, agent_id: str, result: str, message: str) -> Path:
    mailbox = run_dir / "mailbox"
    mailbox.mkdir(exist_ok=True)
    done_path = mailbox / f"{agent_id}.done.md"
    now = datetime.now().isoformat(timespec="seconds")
    done_path.write_text(
        f"""---
agent_id: {agent_id}
status: done
result: {result}
completed_at: {now}
---

# Worker Completion

{message}
""",
        encoding="utf-8",
    )
    status_path = run_dir / "status.yaml"
    existing = status_path.read_text(encoding="utf-8") if status_path.exists() else ""
    if f"{agent_id}: done" not in existing:
        existing = existing.rstrip() + f"\nagents:\n" if "agents:" not in existing else existing.rstrip() + "\n"
        existing += f"  {agent_id}: done\n"
    status_path.write_text(existing, encoding="utf-8")
    summary_path = run_dir / "summary.md"
    if not summary_path.exists():
        summary_path.write_text(f"# Run Summary\n\n{message}\n", encoding="utf-8")
    return done_path


def format_list(items: list[str]) -> str:
    if not items:
        return "- <none declared>"
    return "\n".join(f"- {item}" for item in items)
