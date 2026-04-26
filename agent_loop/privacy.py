from __future__ import annotations

import re
from pathlib import Path

from . import git_utils

POSIX_HOME_PREFIX = "/" + "Users" + "/"
WINDOWS_HOME_PREFIX = "C:" + "\\\\" + "Users" + "\\\\"
GITHUB_CLASSIC_PREFIX = "gh" + "p_"
GITHUB_FINE_GRAINED_PREFIX = "github" + "_pat_"
OPENAI_PREFIX = "s" + "k-"

PATTERNS = [
    ("absolute_path", re.compile(f"({re.escape(POSIX_HOME_PREFIX)}[^\\s`'\"]+|{re.escape(WINDOWS_HOME_PREFIX)}[^\\s`'\"]+)")),
    ("token", re.compile(f"({GITHUB_CLASSIC_PREFIX}[A-Za-z0-9_]{{10,}}|{GITHUB_FINE_GRAINED_PREFIX}[A-Za-z0-9_]+|{OPENAI_PREFIX}[A-Za-z0-9]{{12,}})")),
    ("private_email", re.compile(r"[A-Za-z0-9._%+-]+@(gmail|qq|163|icloud|outlook)\.com")),
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
                match = pattern.search(line)
                if match:
                    findings.append({"type": kind, "file": file, "line": index, "excerpt": redact(line, match.group(0))})
    output = root / ".agent-loop" / "privacy-scan.yaml"
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = ["status: " + ("fail" if findings else "ok"), "findings:"]
    if findings:
        for finding in findings:
            lines.append(f"  - type: {finding['type']}")
            lines.append(f"    file: {finding['file']}")
            if "line" in finding:
                lines.append(f"    line: {finding['line']}")
            if "excerpt" in finding:
                lines.append(f"    excerpt: {finding['excerpt']}")
    else:
        lines.append("  []")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return (1 if findings else 0), output


def redact(line: str, secret: str) -> str:
    return line.replace(secret, "***")[:160]
