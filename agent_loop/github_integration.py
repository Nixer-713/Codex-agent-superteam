from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import git_utils
from .merge_gate import is_merge_ready, is_worktree_run
from .merge_gate import write_risk, write_validation
from .tasks import parse_task
from .runs import run_task_id


@dataclass(frozen=True)
class GithubFinding:
    level: str
    code: str
    message: str


def run_command(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def current_branch(root: Path) -> str:
    result = git_utils.git(root, "branch", "--show-current")
    return result.stdout.strip() if result.returncode == 0 else ""


def origin_url(root: Path) -> str:
    result = git_utils.git(root, "remote", "get-url", "origin")
    return result.stdout.strip() if result.returncode == 0 else ""


def default_branch(root: Path) -> str:
    symbolic = git_utils.git(root, "symbolic-ref", "refs/remotes/origin/HEAD")
    if symbolic.returncode == 0 and symbolic.stdout.strip():
        return symbolic.stdout.strip().split("/")[-1]
    for branch in ["main", "master", "trunk"]:
        exists = git_utils.git(root, "rev-parse", "--verify", branch)
        if exists.returncode == 0:
            return branch
    return "main"


def github_doctor(root: Path) -> list[GithubFinding]:
    findings: list[GithubFinding] = []
    if shutil.which("gh"):
        findings.append(GithubFinding("OK", "github.gh", "gh CLI is installed."))
    else:
        findings.append(GithubFinding("FAIL", "github.gh", "gh CLI is not installed."))
        return findings

    auth = run_command(root, ["gh", "auth", "status"])
    if auth.returncode == 0:
        findings.append(GithubFinding("OK", "github.auth", "gh auth status is valid."))
    else:
        findings.append(GithubFinding("FAIL", "github.auth", "gh is not authenticated."))

    remote = origin_url(root)
    if remote:
        findings.append(GithubFinding("OK", "github.remote", f"origin remote configured: {remote}"))
    else:
        findings.append(GithubFinding("FAIL", "github.remote", "origin remote is missing."))
        return findings

    branch = current_branch(root)
    findings.append(GithubFinding("OK" if branch else "WARN", "github.branch", f"current branch: {branch or 'unknown'}"))

    view = run_command(root, ["gh", "repo", "view", "--json", "name,defaultBranchRef,url"])
    if view.returncode == 0:
        findings.append(GithubFinding("OK", "github.repo_view", "gh can read the repository."))
        try:
            data = json.loads(view.stdout)
            default_name = (data.get("defaultBranchRef") or {}).get("name") or ""
            if default_name:
                findings.append(GithubFinding("OK", "github.default_branch", f"default branch: {default_name}"))
            else:
                findings.append(GithubFinding("WARN", "github.default_branch", "repository has no default branch yet."))
        except json.JSONDecodeError:
            findings.append(GithubFinding("WARN", "github.repo_view_json", "could not parse gh repo view output."))
    else:
        findings.append(GithubFinding("WARN", "github.repo_view", "gh could not read repository metadata."))
    return findings


def render_github_doctor(root: Path, findings: list[GithubFinding]) -> str:
    counts = {"OK": 0, "WARN": 0, "FAIL": 0}
    lines = ["GitHub Doctor", "", f"Root: {root}", ""]
    for finding in findings:
        counts[finding.level] += 1
        lines.append(f"[{finding.level}] {finding.code}: {finding.message}")
    lines.extend(["", "Summary:", f"OK: {counts['OK']}", f"WARN: {counts['WARN']}", f"FAIL: {counts['FAIL']}"])
    return "\n".join(lines) + "\n"


def github_has_failures(findings: list[GithubFinding]) -> bool:
    return any(f.level == "FAIL" for f in findings)


def require_pr_evidence(run_dir: Path) -> None:
    ensure_basic_evidence(run_dir)
    required = ["scope-check.yaml", "risk.yaml", "review.md", "changed-files.txt"]
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise RuntimeError("missing PR evidence: " + ", ".join(missing))
    if is_worktree_run(run_dir) and not is_merge_ready(run_dir):
        raise RuntimeError("worktree run must be merge_ready before GitHub PR creation")
    if "risk: high" in (run_dir / "risk.yaml").read_text(encoding="utf-8"):
        raise RuntimeError("risk is high; GitHub PR creation is blocked")


def ensure_basic_evidence(run_dir: Path) -> None:
    if not (run_dir / "risk.yaml").exists() and (run_dir / "changed-files.txt").exists() and (run_dir / "diff.patch").exists():
        files = [line.strip() for line in (run_dir / "changed-files.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
        write_risk(run_dir / "risk.yaml", files, (run_dir / "diff.patch").read_text(encoding="utf-8"))
    if not (run_dir / "validation.yaml").exists() and (run_dir / "input-task.md").exists():
        write_validation(run_dir / "validation.yaml", parse_task(run_dir / "input-task.md").validation_commands)


def pr_body(root: Path, run_dir: Path) -> Path:
    require_pr_evidence(run_dir)
    task = parse_task(run_dir / "input-task.md")
    task_id = task.task_id
    run_id = run_dir.name
    changed = read_optional(run_dir / "changed-files.txt")
    scope = read_optional(run_dir / "scope-check.yaml")
    risk = read_optional(run_dir / "risk.yaml")
    validation = read_optional(run_dir / "validation.yaml") or "status: not-recorded\n"
    review = read_optional(run_dir / "review.md")
    diff_preview = read_optional(run_dir / "diff.patch")[:2000]
    body = f"""## Task

- Task ID: `{task_id}`
- Task Title: {task.title}
- Run ID: `{run_id}`
- Source: Codex Agent Loop

## Summary

GitHub PR generated from local Codex Agent Loop evidence.

## Changed Files

```text
{changed.rstrip()}
```

## Scope Check

```yaml
{scope.rstrip()}
```

## Risk

```yaml
{risk.rstrip()}
```

## Validation

```yaml
{validation.rstrip()}
```

## Review Evidence

See local run artifact `review.md`.

```text
{review[:1200].rstrip()}
```

## Diff Preview

```diff
{diff_preview.rstrip()}
```

## Evidence Files

- `changed-files.txt`
- `scope-check.yaml`
- `risk.yaml`
- `validation.yaml`
- `review.md`

## Rollback

Use GitHub revert or locally run:

```bash
git revert <merge-or-commit-sha>
```

## Human Gate

- [ ] I reviewed the GitHub diff
- [ ] I reviewed scope-check
- [ ] I reviewed risk
- [ ] I approve merge
"""
    output = run_dir / "github-pr-body.md"
    output.write_text(body, encoding="utf-8")
    return output


def github_pr_create(root: Path, run_dir: Path, draft: bool, dry_run: bool) -> tuple[int, str]:
    body_path = pr_body(root, run_dir)
    branch = current_branch(root)
    default = default_branch(root)
    if not branch:
        raise RuntimeError("current branch is unknown")
    if branch == default or branch in {"main", "master"}:
        raise RuntimeError("github-pr-create refuses to run on the default branch")
    ahead = git_utils.git(root, "rev-list", "--count", f"{default}..{branch}")
    if ahead.returncode != 0:
        raise RuntimeError(f"could not compare {branch} against {default}: {ahead.stderr.strip()}")
    if ahead.stdout.strip() == "0":
        raise RuntimeError(f"no commits ahead of {default}; run accept --commit or commit your changes before creating a PR")
    title = run_task_id(run_dir)
    push_cmd = ["git", "push", "-u", "origin", branch]
    pr_cmd = ["gh", "pr", "create", "--title", title, "--body-file", str(body_path)]
    if draft:
        pr_cmd.append("--draft")
    if dry_run:
        return 0, " ".join(push_cmd) + "\n" + " ".join(pr_cmd)
    push = run_command(root, push_cmd)
    if push.returncode != 0:
        return push.returncode, push.stderr
    pr = run_command(root, pr_cmd)
    return pr.returncode, pr.stdout if pr.returncode == 0 else pr.stderr


def github_pr_sync(root: Path, run_dir: Path, dry_run: bool) -> tuple[int, str]:
    body_path = pr_body(root, run_dir)
    pr_cmd = ["gh", "pr", "edit", "--body-file", str(body_path)]
    if dry_run:
        return 0, " ".join(pr_cmd)
    pr = run_command(root, pr_cmd)
    if pr.returncode == 0:
        (run_dir / "github-pr-sync.yaml").write_text(
            "status: ok\n"
            f"synced_at: {datetime.now(timezone.utc).isoformat()}\n"
            f"body_file: {body_path.name}\n"
            f"command: {' '.join(pr_cmd)}\n",
            encoding="utf-8",
        )
    return pr.returncode, pr.stdout if pr.returncode == 0 else pr.stderr


def read_optional(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""
