from __future__ import annotations

import subprocess
from pathlib import Path


def git(root: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def is_git_repository(root: Path) -> bool:
    result = git(root, "rev-parse", "--is-inside-work-tree")
    return result.returncode == 0 and result.stdout.strip() == "true"


def require_git_repository(root: Path) -> None:
    if not is_git_repository(root):
        raise ValueError(f"root is not a Git repository: {root}. Run `git init` or pass the correct --root path.")


def current_head(root: Path) -> str:
    result = git(root, "rev-parse", "HEAD")
    if result.returncode != 0:
        return "NO_GIT_HEAD"
    return result.stdout.strip()


def status_short(root: Path) -> str:
    result = git(root, "status", "--short")
    if result.returncode != 0:
        return result.stderr.strip()
    return result.stdout


INTERNAL_PREFIXES = (".agent-loop/", ".agent-runs/", ".locks/", ".tasks/", "mailbox/")


def diff_name_only(root: Path) -> list[str]:
    result = git(root, "diff", "--name-only")
    untracked = git(root, "ls-files", "--others", "--exclude-standard")
    names: list[str] = []
    if result.returncode == 0:
        names.extend(line.strip() for line in result.stdout.splitlines() if line.strip())
    if untracked.returncode == 0:
        names.extend(line.strip() for line in untracked.stdout.splitlines() if line.strip())
    return sorted(
        name
        for name in dict.fromkeys(names)
        if not name.startswith(INTERNAL_PREFIXES)
    )


def diff_stat(root: Path) -> str:
    result = git(root, "diff", "--stat")
    return result.stdout if result.returncode == 0 else result.stderr


def full_diff(root: Path) -> str:
    tracked = git(root, "diff")
    output = tracked.stdout if tracked.returncode == 0 else tracked.stderr
    untracked_files = diff_name_only(root)
    tracked_names = set()
    tracked_result = git(root, "diff", "--name-only")
    if tracked_result.returncode == 0:
        tracked_names = {line.strip() for line in tracked_result.stdout.splitlines() if line.strip()}
    untracked_only = [name for name in untracked_files if name not in tracked_names]
    for name in untracked_only:
        path = root / name
        if path.is_file():
            output += f"\n--- /dev/null\n+++ b/{name}\n"
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    output += f"+{line}\n"
            except UnicodeDecodeError:
                output += "+<binary or non-utf8 file>\n"
    return output
