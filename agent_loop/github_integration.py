from __future__ import annotations

import json
import shutil
import subprocess
import time
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


def evaluate_pr_gate(expected_files: list[str], pr_data: dict) -> dict:
    pr_files = sorted(file.get("path", "") for file in pr_data.get("files", []) if file.get("path"))
    expected = sorted(expected_files)
    checks = pr_data.get("statusCheckRollup", [])
    failed_checks = sorted(
        check.get("name", "unknown")
        for check in checks
        if check.get("status") == "COMPLETED" and check.get("conclusion") not in {"SUCCESS", "SKIPPED"}
    )
    pending_checks = sorted(check.get("name", "unknown") for check in checks if check.get("status") != "COMPLETED")
    result = {
        "status": "ok",
        "url": pr_data.get("url", ""),
        "state": pr_data.get("state", ""),
        "draft": bool(pr_data.get("isDraft")),
        "head": pr_data.get("headRefName", ""),
        "base": pr_data.get("baseRefName", ""),
        "expected_files": expected,
        "pr_files": pr_files,
        "missing_pr_files": sorted(set(expected) - set(pr_files)),
        "extra_pr_files": sorted(set(pr_files) - set(expected)),
        "files_match": expected == pr_files,
        "failed_checks": failed_checks,
        "pending_checks": pending_checks,
        "checks_passed": bool(checks) and not failed_checks and not pending_checks,
    }
    if result["draft"] or pr_data.get("state") != "OPEN" or not result["files_match"] or not result["checks_passed"]:
        result["status"] = "fail"
    return result


def summarize_ci_runs(head_sha: str, runs: list[dict]) -> dict:
    matching = [run for run in runs if run.get("headSha") == head_sha]
    run_ids = [run.get("databaseId") for run in matching]
    failed = [run for run in matching if run.get("status") == "completed" and run.get("conclusion") != "success"]
    pending = [run for run in matching if run.get("status") != "completed"]
    status = "missing"
    if failed:
        status = "failure"
    elif pending:
        status = "in_progress"
    elif matching:
        status = "success"
    return {
        "status": status,
        "head_sha": head_sha,
        "run_ids": run_ids,
        "failed_run_ids": [run.get("databaseId") for run in failed],
        "pending_run_ids": [run.get("databaseId") for run in pending],
        "runs": matching,
    }


def github_ci_watch(root: Path, timeout: float, poll: float) -> tuple[int, str]:
    head = git_utils.git(root, "rev-parse", "HEAD")
    if head.returncode != 0:
        raise RuntimeError(head.stderr.strip())
    head_sha = head.stdout.strip()
    branch = current_branch(root)
    deadline = time.time() + timeout
    summary: dict = {"status": "missing", "head_sha": head_sha}
    while True:
        result = run_command(
            root,
            [
                "gh",
                "run",
                "list",
                "--branch",
                branch,
                "--limit",
                "20",
                "--json",
                "databaseId,event,status,conclusion,workflowName,headSha,url,createdAt",
            ],
        )
        if result.returncode != 0:
            return result.returncode, result.stderr
        summary = summarize_ci_runs(head_sha, json.loads(result.stdout or "[]"))
        if summary["status"] in {"success", "failure"} or time.time() >= deadline:
            break
        time.sleep(poll)
    output = root / ".agent-loop" / "github-ci-watch.yaml"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_mapping(summary), encoding="utf-8")
    return (0 if summary["status"] == "success" else 1), render_mapping(summary)


def github_pr_check(root: Path, run_dir: Path) -> tuple[int, str]:
    require_pr_evidence(run_dir)
    expected = [line.strip() for line in (run_dir / "changed-files.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    result = run_command(
        root,
        [
            "gh",
            "pr",
            "view",
            "--json",
            "url,isDraft,state,headRefName,baseRefName,files,statusCheckRollup",
        ],
    )
    if result.returncode != 0:
        return result.returncode, result.stderr
    gate = evaluate_pr_gate(expected, json.loads(result.stdout))
    output = run_dir / "github-pr-check.yaml"
    output.write_text(render_mapping(gate), encoding="utf-8")
    return (0 if gate["status"] == "ok" else 1), render_mapping(gate)


def render_mapping(data: dict) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        elif isinstance(value, list):
            lines.append(f"{key}:")
            if value:
                for item in value:
                    lines.append(f"  - {json.dumps(item, ensure_ascii=False)}")
            else:
                lines.append("  []")
        elif isinstance(value, dict):
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def read_optional(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""
