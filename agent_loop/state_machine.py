from __future__ import annotations

from pathlib import Path

from . import git_utils
from .config import load_config
from .review import create_review
from .scope_guard import check_scope, write_scope_report
from .tasks import parse_task
from .merge_gate import write_risk, write_validation


SAFE_EVIDENCE = ["changed-files.txt", "diff-stat.txt", "diff.patch", "scope-check.yaml", "risk.yaml", "validation.yaml", "review.md"]


def run_state(root: Path, run_dir: Path) -> dict:
    missing = [name for name in SAFE_EVIDENCE if not (run_dir / name).exists()]
    status_text = (run_dir / "status.yaml").read_text(encoding="utf-8") if (run_dir / "status.yaml").exists() else ""
    worker = read_worker_state(run_dir)
    if (run_dir / "mailbox").exists() and list((run_dir / "mailbox").glob("*.blocked.md")):
        phase = "blocked"
    elif worker.get("status") == "failed":
        phase = "blocked"
    elif worker.get("status") == "running":
        phase = "dispatched"
    elif "status: accepted" in status_text:
        phase = "accepted"
    elif (run_dir / "github-pr-check.yaml").exists() and "status: ok" in (run_dir / "github-pr-check.yaml").read_text(encoding="utf-8"):
        phase = "github_pr_ready"
    elif (run_dir / "merge-result.yaml").exists() and "match: true" in (run_dir / "merge-result.yaml").read_text(encoding="utf-8"):
        phase = "merge_ready"
    elif (run_dir / "merge-preflight.yaml").exists() and "status: ok" in (run_dir / "merge-preflight.yaml").read_text(encoding="utf-8"):
        phase = "merge_preflight_ready"
    elif (run_dir / "review.md").exists() and not missing:
        phase = "review_ready"
    elif (run_dir / "mailbox").exists() and list((run_dir / "mailbox").glob("*.done.md")):
        phase = "worker_done"
    elif any(run_dir.glob("*.prompt.md")):
        phase = "dispatched"
    else:
        phase = "created"
    return {
        "run_id": run_dir.name,
        "phase": phase,
        "worker_status": worker.get("status", ""),
        "worker_exit_code": worker.get("exit_code", ""),
        "worker_failure": worker.get("failure", ""),
        "missing_evidence": missing,
        "next_command": next_command(run_dir.name, missing, phase),
    }


def read_worker_state(run_dir: Path) -> dict:
    evidence = run_dir / "orchestrate-worker.yaml"
    if not evidence.exists():
        return {}
    data: dict[str, str] = {}
    for line in evidence.read_text(encoding="utf-8").splitlines():
        if ":" in line and not line.startswith("  "):
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


def next_command(run_id: str, missing: list[str], phase: str) -> str:
    if phase in {"blocked", "accepted", "github_pr_ready"}:
        return "human_review"
    if missing:
        return f"agent-loop resume {run_id} --root <project>"
    if phase == "review_ready":
        return f"agent-loop accept {run_id} --root <project>"
    return f"agent-loop watch {run_id} --root <project>"


def resume_run(root: Path, run_dir: Path) -> dict:
    config = load_config(root)
    if (run_dir / "mailbox").exists() and list((run_dir / "mailbox").glob("*.blocked.md")):
        return run_state(root, run_dir)
    changed = git_utils.diff_name_only(root)
    if not (run_dir / "changed-files.txt").exists():
        (run_dir / "changed-files.txt").write_text("\n".join(changed) + ("\n" if changed else ""), encoding="utf-8")
    if not (run_dir / "diff-stat.txt").exists():
        (run_dir / "diff-stat.txt").write_text(git_utils.diff_stat(root), encoding="utf-8")
    if not (run_dir / "diff.patch").exists():
        (run_dir / "diff.patch").write_text(git_utils.full_diff(root), encoding="utf-8")
    task = parse_task(run_dir / "input-task.md")
    changed = (run_dir / "changed-files.txt").read_text(encoding="utf-8").splitlines()
    if not (run_dir / "scope-check.yaml").exists():
        write_scope_report(run_dir / "scope-check.yaml", check_scope(task, changed))
    if "status: violation" in (run_dir / "scope-check.yaml").read_text(encoding="utf-8"):
        return run_state(root, run_dir)
    if not (run_dir / "risk.yaml").exists():
        write_risk(run_dir / "risk.yaml", changed, (run_dir / "diff.patch").read_text(encoding="utf-8"), config.get("risk", {}))
    if "risk: high" in (run_dir / "risk.yaml").read_text(encoding="utf-8"):
        return run_state(root, run_dir)
    if not (run_dir / "validation.yaml").exists():
        write_validation(run_dir / "validation.yaml", task.validation_commands)
    if not (run_dir / "review.md").exists():
        create_review(run_dir)
    status = run_dir / "status.yaml"
    text = status.read_text(encoding="utf-8")
    if "phase: review_ready" not in text:
        status.write_text(text.rstrip() + "\nphase: review_ready\n", encoding="utf-8")
    return run_state(root, run_dir)
