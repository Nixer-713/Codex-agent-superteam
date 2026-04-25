from __future__ import annotations

from pathlib import Path


def create_final_report(run_dir: Path) -> Path:
    report = run_dir / "final-report.md"
    sections = {
        "Changed Files": "changed-files.txt",
        "Scope": "scope-check.yaml",
        "Risk": "risk.yaml",
        "Validation": "validation.yaml",
        "Review": "review-decision.yaml",
        "GitHub PR": "github-pr-check.yaml",
        "Privacy": "privacy-scan.yaml",
    }
    missing = [name for name in sections.values() if not (run_dir / name).exists()]
    decision = "accept" if not missing else "revise"
    lines = ["# Final Report", "", f"Run ID: `{run_dir.name}`", "", "## Recommended Decision", "", decision, "", "## Missing Evidence"]
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
