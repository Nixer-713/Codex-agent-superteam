from __future__ import annotations

import re
from pathlib import Path

from .privacy import privacy_scan


def release_check(root: Path) -> tuple[int, Path, Path]:
    privacy_code, privacy_output = privacy_scan(root)
    version = package_version(root)
    has_package_metadata = (root / "pyproject.toml").exists()
    tag_name = matching_version_tag_exists(root, version) if version else ""
    tag_ok = (not has_package_metadata) or bool(version and tag_name)
    checks = [
        ("privacy", privacy_code == 0, privacy_output.name),
        ("package_version", (not has_package_metadata) or bool(version), version or "not-applicable"),
        ("version_tag", tag_ok, tag_name or (f"v{version}*" if version else "not-applicable")),
        ("readme", (root / "README.md").exists(), "README.md"),
    ]
    status = "ok" if all(ok for _, ok, _ in checks) else "fail"
    output = root / ".agent-loop" / "release-check.yaml"
    report = root / ".agent-loop" / "release-check.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"status: {status}", "checks:"]
    for name, ok, detail in checks:
        lines.append(f"  - name: {name}")
        lines.append(f"    status: {'ok' if ok else 'fail'}")
        lines.append(f"    detail: {detail}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    md = ["# Release Check", "", f"Status: {'OK' if status == 'ok' else 'FAIL'}", ""]
    for name, ok, detail in checks:
        md.append(f"- {'OK' if ok else 'FAIL'} {name}: {detail}")
    report.write_text("\n".join(md) + "\n", encoding="utf-8")
    return (0 if status == "ok" else 1), output, report


def package_version(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return ""
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else ""


def tag_exists(root: Path, tag: str) -> bool:
    git_dir = root / ".git"
    return (git_dir / "refs" / "tags" / tag).exists()


def matching_version_tag_exists(root: Path, version: str) -> str:
    if not version:
        return ""
    tags = root / ".git" / "refs" / "tags"
    if not tags.exists():
        return ""
    for tag in tags.iterdir():
        if tag.name == f"v{version}" or tag.name.startswith(f"v{version}-"):
            return tag.name
    return ""
