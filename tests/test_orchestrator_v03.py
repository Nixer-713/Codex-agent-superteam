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


def create_task(root: Path, title: str, allowed: str):
    result = run_cli("new-task", title, "--root", str(root), "--allowed", allowed)
    assert result.returncode == 0, result.stderr


def test_orchestrate_parallel_starts_distinct_agents_and_evidence(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    create_task(root, "Docs A", "docs/a/**")
    create_task(root, "Docs B", "docs/b/**")
    create_task(root, "Docs C", "docs/c/**")

    result = run_cli("orchestrate", "--root", str(root), "--parallel", "3")

    assert result.returncode == 0, result.stderr
    runs = sorted((root / ".agent-runs").iterdir())
    assert len(runs) == 3
    assert (root / ".agent-loop" / "orchestrate-result.yaml").is_file()
    assert (root / ".agent-loop" / "orchestrate-report.md").is_file()
    agent_ids = []
    for run_dir in runs:
        evidence = run_dir / "orchestrate-worker.yaml"
        assert evidence.is_file()
        text = evidence.read_text(encoding="utf-8")
        assert "status: started" in text
        agent_line = next(line for line in text.splitlines() if line.startswith("agent_id:"))
        agent_id = agent_line.split(":", 1)[1].strip()
        agent_ids.append(agent_id)
        assert (run_dir / f"{agent_id}.prompt.md").is_file()
        assert (run_dir / f"{agent_id}.codex-command.sh").is_file()
    assert agent_ids == ["worker-1", "worker-2", "worker-3"]


def test_orchestrate_blocks_overlapping_allowed_paths(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    create_task(root, "Docs All", "docs/**")
    create_task(root, "Docs API", "docs/api/**")
    create_task(root, "Src", "src/**")

    result = run_cli("orchestrate", "--root", str(root), "--parallel", "3")

    assert result.returncode == 0, result.stderr
    runs = list((root / ".agent-runs").iterdir())
    assert len(runs) == 2
    report = (root / ".agent-loop" / "orchestrate-report.md").read_text(encoding="utf-8")
    result_yaml = (root / ".agent-loop" / "orchestrate-result.yaml").read_text(encoding="utf-8")
    assert "blocked_tasks" in result_yaml
    assert "Docs API" in report
    assert len(list((root / ".tasks" / "pending").glob("*.md"))) == 1


def test_orchestrate_worktree_writes_worktree_metadata(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    create_task(root, "Docs Worktree", "docs/worktree/**")

    result = run_cli("orchestrate", "--root", str(root), "--parallel", "1", "--worktree")

    assert result.returncode == 0, result.stderr
    run_dir = next((root / ".agent-runs").iterdir())
    worker = (run_dir / "orchestrate-worker.yaml").read_text(encoding="utf-8")
    assert "worktree_path:" in worker
    assert "branch: codex/" in worker
    assert (run_dir / "worktrees.yaml").is_file()


def test_orchestrate_watch_done_and_blocked_are_isolated(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    create_task(root, "Done Task", "docs/done/**")
    create_task(root, "Blocked Task", "docs/blocked/**")
    start = run_cli("orchestrate", "--root", str(root), "--parallel", "2")
    assert start.returncode == 0, start.stderr
    runs = sorted((root / ".agent-runs").iterdir())
    (root / "docs" / "done").mkdir(parents=True)
    (root / "docs" / "done" / "ok.md").write_text("# OK\n", encoding="utf-8")
    (runs[0] / "mailbox" / "worker-1.done.md").write_text("agent_id: worker-1\nstatus: done\nchanged_files:\n  - docs/done/ok.md\nsummary: ok\n", encoding="utf-8")
    (runs[1] / "mailbox" / "worker-2.blocked.md").write_text("agent_id: worker-2\nstatus: blocked\nreason: blocked\n", encoding="utf-8")

    watched = run_cli("orchestrate", "--root", str(root), "--watch", "--parallel", "2")

    assert watched.returncode == 0, watched.stderr
    assert (runs[0] / "review.md").is_file()
    assert "status: review_ready" in (runs[0] / "orchestrate-worker.yaml").read_text(encoding="utf-8")
    assert "status: blocked" in (runs[1] / "orchestrate-worker.yaml").read_text(encoding="utf-8")
    report = (root / ".agent-loop" / "orchestrate-report.md").read_text(encoding="utf-8")
    assert "review_ready" in report
    assert "blocked" in report
