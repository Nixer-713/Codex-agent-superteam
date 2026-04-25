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
    decision = (run_dir / "review-decision.yaml").read_text(encoding="utf-8") if (run_dir / "review-decision.yaml").exists() else ""
    review = (run_dir / "review.md").read_text(encoding="utf-8") if (run_dir / "review.md").exists() else ""
    prompt = run_dir / f"{agent_id}.revise.prompt.md"
    prompt.write_text(
        "# Codex Revision Prompt\n\n"
        "Revise only the existing task changes. Do not expand scope.\n\n"
        "## Review Decision\n\n"
        f"{decision}\n\n"
        "## Review Evidence\n\n"
        f"{review[:4000]}\n",
        encoding="utf-8",
    )
    return prompt
