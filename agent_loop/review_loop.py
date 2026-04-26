from __future__ import annotations

from datetime import datetime
from pathlib import Path

VALID_DECISIONS = {"accept", "revise", "split", "rollback", "escalate"}


def write_review_result(run_dir: Path, decision: str, reason: str) -> Path:
    if decision not in VALID_DECISIONS:
        raise ValueError("invalid review decision")
    path = run_dir / "review-decision.yaml"
    path.write_text(
        f"decision: {decision}\nreason: {reason}\ndecided_at: {datetime.now().isoformat(timespec='seconds')}\n",
        encoding="utf-8",
    )
    return path


def decision_blocks_accept(run_dir: Path) -> str:
    path = run_dir / "review-decision.yaml"
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("decision:"):
            decision = line.split(":", 1)[1].strip()
            return "" if decision == "accept" else decision
    return ""


def create_revise_prompt(run_dir: Path, agent_id: str) -> Path:
    decision = read_text(run_dir / "review-decision.yaml")
    review = read_text(run_dir / "review.md")
    github_comments = read_text(run_dir / "github-review-comments.md")
    changed = read_text(run_dir / "changed-files.txt")
    task = read_text(run_dir / "input-task.md")
    attempt_dir = run_dir / "attempts"
    attempt_dir.mkdir(exist_ok=True)
    attempt_id = f"attempt-{len(list(attempt_dir.glob('*.revise.prompt.md'))) + 1}"
    prompt = attempt_dir / f"{attempt_id}.revise.prompt.md"
    prompt.write_text(
        "# Codex Revision Prompt\n\n"
        f"Parent run: {run_dir.name}\n"
        f"Agent ID: {agent_id}\n\n"
        "Revise only the existing task changes. Do not expand scope.\n\n"
        "## Original Task And Scope\n\n"
        f"{task[:3000]}\n\n"
        "## Changed Files\n\n"
        f"{changed[:2000]}\n\n"
        "## Review Decision\n\n"
        f"{decision}\n\n"
        "## GitHub Review Comments\n\n"
        f"{github_comments[:4000]}\n\n"
        "## Local Review Evidence\n\n"
        f"{review[:3000]}\n",
        encoding="utf-8",
    )
    (run_dir / "revise-attempt.yaml").write_text(
        f"parent_run_id: {run_dir.name}\n"
        f"attempt_id: {attempt_id}\n"
        f"agent_id: {agent_id}\n"
        "source_comments: github-review-comments.yaml\n"
        f"prompt: attempts/{prompt.name}\n",
        encoding="utf-8",
    )
    legacy = run_dir / f"{agent_id}.revise.prompt.md"
    legacy.write_text(prompt.read_text(encoding="utf-8"), encoding="utf-8")
    return prompt


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""
