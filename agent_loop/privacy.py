from __future__ import annotations

import re
from pathlib import Path

from . import git_utils

PATTERNS = [
    ("absolute_path", re.compile(r"(/Users/[^\s`'\"]+|C:\\\\Users\\\\[^\s`'\"]+)")),
    ("token", re.compile(r"(ghp_[A-Za-z0-9_]{10,}|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9]{12,})")),
    ("private_email", re.compile(r"[A-Za-z0-9._%+-]+@(gmail|qq|163|icloud|outlook)\\.com")),
]
FORBIDDEN_TRACKED = {".agent-runs", ".tasks", ".locks"}


def privacy_scan(root: Path) -> tuple[int, Path]:
    files_result = git_utils.git(root, "ls-files")
    files = files_result.stdout.splitlines() if files_result.returncode == 0 else []
    findings: list[dict] = []
    for file in files:
        if file.split("/", 1)[0] in FORBIDDEN_TRACKED:
            findings.append({"type": "tracked_artifact", "file": file})
            continue
        path = root / file
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for index, line in enumerate(text.splitlines(), start=1):
            for kind, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append({"type": kind, "file": file, "line": index})
    output = root / ".agent-loop" / "privacy-scan.yaml"
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = ["status: " + ("fail" if findings else "ok"), "findings:"]
    if findings:
        for finding in findings:
            lines.append(f"  - type: {finding['type']}")
            lines.append(f"    file: {finding['file']}")
            if "line" in finding:
                lines.append(f"    line: {finding['line']}")
    else:
        lines.append("  []")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return (1 if findings else 0), output
