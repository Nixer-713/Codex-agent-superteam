import json
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


def create_review_ready_run(root: Path) -> str:
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Review feedback", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    run_id = started.stdout.strip().split()[-1]
    (root / "docs").mkdir()
    (root / "docs" / "feedback.md").write_text("# Feedback\n", encoding="utf-8")
    assert run_cli("complete", run_id, "--root", str(root), "--agent-id", "worker-1").returncode == 0
    assert run_cli("resume", run_id, "--root", str(root)).returncode == 0
    return run_id


def write_comments(path: Path):
    path.write_text(
        json.dumps(
            {
                "comments": [
                    {
                        "id": "PRRC_1",
                        "author": {"login": "reviewer-one"},
                        "path": "docs/feedback.md",
                        "line": 3,
                        "body": "Please clarify the rollback step.",
                        "url": "https://github.com/example/repo/pull/1#discussion_r1",
                        "createdAt": "2026-04-26T00:00:00Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_github_pr_comments_file_drives_revise_attempt_and_report(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    run_id = create_review_ready_run(root)
    comments = tmp_path / "comments.json"
    write_comments(comments)

    imported = run_cli("github-pr-comments", run_id, "--root", str(root), "--from-file", str(comments))
    decision = run_cli("review-result", run_id, "--root", str(root), "--from-github-comments")
    accept = run_cli("accept", run_id, "--root", str(root))
    revise = run_cli("revise", run_id, "--root", str(root), "--agent-id", "worker-1")
    report = run_cli("report", run_id, "--root", str(root))

    run_dir = root / ".agent-runs" / run_id
    assert imported.returncode == 0, imported.stderr
    assert decision.returncode == 0, decision.stderr
    assert accept.returncode == 1
    assert revise.returncode == 0, revise.stderr
    assert report.returncode == 0, report.stderr
    assert "decision: revise" in (run_dir / "review-decision.yaml").read_text(encoding="utf-8")
    assert "github-review-comments.yaml" in (run_dir / "review-decision.yaml").read_text(encoding="utf-8")
    assert "Please clarify the rollback step." in (run_dir / "github-review-comments.md").read_text(encoding="utf-8")
    attempt = run_dir / "attempts" / "attempt-1.revise.prompt.md"
    assert attempt.is_file()
    prompt = attempt.read_text(encoding="utf-8")
    assert run_id in prompt
    assert "docs/feedback.md" in prompt
    assert "line: 3" in prompt
    assert "Please clarify the rollback step." in prompt
    assert (run_dir / "revise-attempt.yaml").is_file()
    final_report = (run_dir / "final-report.md").read_text(encoding="utf-8")
    assert "GitHub Review Feedback" in final_report
    assert "revise" in final_report


def test_empty_github_pr_comments_do_not_force_revise(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    run_id = create_review_ready_run(root)
    comments = tmp_path / "comments.json"
    comments.write_text('{"comments": []}', encoding="utf-8")

    imported = run_cli("github-pr-comments", run_id, "--root", str(root), "--from-file", str(comments))
    decision = run_cli("review-result", run_id, "--root", str(root), "--from-github-comments")

    run_dir = root / ".agent-runs" / run_id
    assert imported.returncode == 0, imported.stderr
    assert decision.returncode == 1
    assert "no GitHub review comments" in decision.stderr
    assert "comments: []" in (run_dir / "github-review-comments.yaml").read_text(encoding="utf-8")
