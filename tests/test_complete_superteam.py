import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "agent_loop.cli", *args],
        cwd=cwd or PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git(repo, *args):
    result = subprocess.run(["git", *args], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert result.returncode == 0, result.stderr
    return result


def init_git_repo(root: Path):
    git(root, "init")
    git(root, "config", "user.email", "agent-loop@example.invalid")
    git(root, "config", "user.name", "Agent Loop")
    (root / "README.md").write_text("# Repo\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "initial commit")


def test_config_defaults_are_used_for_new_tasks(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    config = root / ".agent-loop" / "config.yaml"
    config.write_text("validation:\n  default_commands:\n    - python3 -m pytest -q\n", encoding="utf-8")

    result = run_cli("new-task", "Configured validation", "--root", str(root), "--allowed", "docs/**")

    assert result.returncode == 0, result.stderr
    task = next((root / ".tasks" / "pending").glob("*.md"))
    assert "python3 -m pytest -q" in task.read_text(encoding="utf-8")


def test_state_and_resume_fill_safe_missing_evidence(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "State docs", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    run_id = started.stdout.strip().split()[-1]
    (root / "docs").mkdir()
    (root / "docs" / "state.md").write_text("# State\n", encoding="utf-8")
    assert run_cli("complete", run_id, "--root", str(root), "--agent-id", "worker-1").returncode == 0

    state_before = run_cli("state", run_id, "--root", str(root))
    resume = run_cli("resume", run_id, "--root", str(root))
    state_after = run_cli("state", run_id, "--root", str(root))

    assert state_before.returncode == 0
    assert "missing_evidence" in state_before.stdout
    assert resume.returncode == 0, resume.stderr
    assert "review_ready" in state_after.stdout
    assert (root / ".agent-runs" / run_id / "review.md").is_file()


def test_privacy_scan_blocks_private_paths_and_tokens(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    secret = root / "secret.md"
    private_path = "/" + "Users" + "/example/project"
    fake_token = "github" + "_pat_" + "1234567890abcdef"
    secret.write_text(f"private {private_path} and {fake_token}\n", encoding="utf-8")
    git(root, "add", "secret.md")

    result = run_cli("privacy-scan", "--root", str(root))

    assert result.returncode == 1
    assert "privacy-scan.yaml" in result.stdout
    assert "absolute_path" in (root / ".agent-loop" / "privacy-scan.yaml").read_text(encoding="utf-8")
    assert "token" in (root / ".agent-loop" / "privacy-scan.yaml").read_text(encoding="utf-8")


def test_report_lists_missing_and_recommended_decision(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Report docs", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    run_id = started.stdout.strip().split()[-1]

    result = run_cli("report", run_id, "--root", str(root))

    assert result.returncode == 0, result.stderr
    report = root / ".agent-runs" / run_id / "final-report.md"
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "Recommended Decision" in text
    assert "missing" in text


def test_release_check_requires_privacy_and_tests_metadata(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0

    result = run_cli("release-check", "--root", str(root))

    assert result.returncode == 0, result.stderr
    assert "release-check.yaml" in result.stdout
    assert (root / ".agent-loop" / "release-check.yaml").is_file()


def test_github_issue_import_dry_run_parses_task_fields(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    issue = tmp_path / "issue.json"
    issue.write_text(
        '{"number": 7, "title": "Add docs", "body": "allowed: docs/**\\nforbidden: secrets/**\\nvalidation: python3 -m pytest -q"}',
        encoding="utf-8",
    )

    result = run_cli("github-issue-import", "7", "--root", str(root), "--from-file", str(issue))

    assert result.returncode == 0, result.stderr
    task = next((root / ".tasks" / "pending").glob("*.md"))
    text = task.read_text(encoding="utf-8")
    assert "Add docs" in text
    assert "docs/**" in text
    assert "secrets/**" in text


def test_review_result_blocks_accept_and_revise_writes_prompt(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Revise docs", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    run_id = started.stdout.strip().split()[-1]
    (root / "docs").mkdir()
    (root / "docs" / "revise.md").write_text("# Revise\n", encoding="utf-8")
    assert run_cli("complete", run_id, "--root", str(root), "--agent-id", "worker-1").returncode == 0
    assert run_cli("resume", run_id, "--root", str(root)).returncode == 0

    decision = run_cli("review-result", run_id, "--root", str(root), "--decision", "revise", "--reason", "Need clearer docs")
    accept = run_cli("accept", run_id, "--root", str(root))
    revise = run_cli("revise", run_id, "--root", str(root), "--agent-id", "worker-1")

    assert decision.returncode == 0, decision.stderr
    assert accept.returncode == 1
    assert "review decision is revise" in accept.stderr
    assert revise.returncode == 0, revise.stderr
    prompt = root / ".agent-runs" / run_id / "worker-1.revise.prompt.md"
    assert prompt.is_file()
    assert "Need clearer docs" in prompt.read_text(encoding="utf-8")


def test_orchestrate_starts_multiple_pending_tasks_without_accepting(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    for title, allowed in [("Docs A", "docs/a/**"), ("Docs B", "docs/b/**"), ("Docs C", "docs/c/**")]:
        assert run_cli("new-task", title, "--root", str(root), "--allowed", allowed).returncode == 0

    result = run_cli("orchestrate", "--root", str(root), "--parallel", "2")

    assert result.returncode == 0, result.stderr
    runs = list((root / ".agent-runs").iterdir())
    assert len(runs) == 2
    assert len(list((root / ".tasks" / "active").glob("*.md"))) == 2
    assert len(list((root / ".tasks" / "done").glob("*.md"))) == 0
    for run_dir in runs:
        evidence = (run_dir / "orchestrate-worker.yaml").read_text(encoding="utf-8")
        agent_id = next(line.split(":", 1)[1].strip() for line in evidence.splitlines() if line.startswith("agent_id:"))
        assert (run_dir / f"{agent_id}.prompt.md").is_file()


def test_config_risk_threshold_changes_resume_risk(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    (root / ".agent-loop" / "config.yaml").write_text(
        "risk:\n  low_files: 0\n  low_lines: 0\n  medium_files: 0\n  medium_lines: 0\n",
        encoding="utf-8",
    )
    assert run_cli("new-task", "Risk docs", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    run_id = started.stdout.strip().split()[-1]
    (root / "docs").mkdir()
    (root / "docs" / "risk.md").write_text("# Risk\n", encoding="utf-8")
    assert run_cli("complete", run_id, "--root", str(root)).returncode == 0

    assert run_cli("resume", run_id, "--root", str(root)).returncode == 0

    assert "risk: high" in (root / ".agent-runs" / run_id / "risk.yaml").read_text(encoding="utf-8")


def test_github_issue_comment_and_pr_comments_dry_run(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Issue comment", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    run_id = started.stdout.strip().split()[-1]

    issue_comment = run_cli("github-issue-comment", run_id, "--root", str(root), "--issue", "7", "--dry-run")
    pr_comments = run_cli("github-pr-comments", run_id, "--root", str(root), "--from-file", str(root / "missing.json"), "--dry-run")

    assert issue_comment.returncode == 0, issue_comment.stderr
    assert "gh issue comment 7" in issue_comment.stdout
    assert pr_comments.returncode == 0, pr_comments.stderr
    assert (root / ".agent-runs" / run_id / "pr-comments.md").is_file()


def test_doctor_fails_on_invalid_config(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    (root / ".agent-loop" / "config.yaml").write_text("  bad-indent: true\n", encoding="utf-8")

    result = run_cli("doctor", "--root", str(root))

    assert result.returncode == 1
    assert "config.parse" in result.stdout
