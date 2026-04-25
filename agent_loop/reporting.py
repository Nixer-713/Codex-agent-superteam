from __future__ import annotations

from pathlib import Path


def create_final_report(run_dir: Path) -> Path:
    report = run_dir / "final-report.md"
    sections = {
        "Worker Lifecycle": "orchestrate-worker.yaml",
        "Changed Files": "changed-files.txt",
        "Scope": "scope-check.yaml",
        "Risk": "risk.yaml",
        "Validation": "validation.yaml",
        "Review": "review-decision.yaml",
        "Merge Result": "merge-result.yaml",
        "GitHub PR": "github-pr-check.yaml",
        "Privacy": "privacy-scan.yaml",
    }
    required = ["changed-files.txt", "scope-check.yaml", "risk.yaml", "validation.yaml"]
    missing = [name for name in required if not (run_dir / name).exists()]
    worker = read_simple_yaml(run_dir / "orchestrate-worker.yaml")
    decision = recommended_decision(run_dir, missing, worker)
    lines = [
        "# Final Report",
        "",
        f"Run ID: `{run_dir.name}`",
        "",
        "## Recommended Decision",
        "",
        decision,
        "",
        "## Worker Summary",
        "",
        f"- status: {worker.get('status', 'unknown')}",
        f"- exit_code: {worker.get('exit_code', 'unknown')}",
        f"- duration_seconds: {worker.get('duration_seconds', 'unknown')}",
        f"- stdout_log: {worker.get('stdout_log', 'missing')}",
        f"- stderr_log: {worker.get('stderr_log', 'missing')}",
        f"- failure: {worker.get('failure', 'none')}",
        "",
        "## Missing Required Evidence",
    ]
    if missing:
        lines.extend(f"- {item}" for item in missing)
    else:
        lines.append("- none")
    for title, filename in sections.items():
        lines.extend(["", f"## {title}", "", "```text"])
        path = run_dir / filename
        lines.append(path.read_text(encoding="utf-8")[:2000] if path.exists() else "missing")
        lines.append("```")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def read_simple_yaml(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line and not line.startswith("  "):
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


def recommended_decision(run_dir: Path, missing: list[str], worker: dict[str, str]) -> str:
    if worker.get("status") in {"failed", "blocked"}:
        return "revise"
    if missing:
        return "revise"
    if (run_dir / "risk.yaml").exists() and "risk: high" in (run_dir / "risk.yaml").read_text(encoding="utf-8"):
        return "escalate"
    if (run_dir / "review-decision.yaml").exists() and "decision: accept" in (run_dir / "review-decision.yaml").read_text(encoding="utf-8"):
        return "accept"
    return "human_review"
