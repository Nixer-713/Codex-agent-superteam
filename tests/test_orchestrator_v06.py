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


def test_orchestrate_writes_durable_state(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    create_task(root, "State A", "docs/a/**")
    create_task(root, "State B", "docs/b/**")

    result = run_cli("orchestrate", "--root", str(root), "--parallel", "2")
    state = run_cli("orchestrate-state", "--root", str(root))

    state_file = root / ".agent-loop" / "orchestrator-state.yaml"
    assert result.returncode == 0, result.stderr
    assert state.returncode == 0, state.stderr
    assert state_file.is_file()
    text = state_file.read_text(encoding="utf-8")
    assert "orchestration_id:" in text
    assert "parallel: 2" in text
    assert "worker-1" in text
    assert "worker-2" in text
    assert "last_seen_at:" in text
    assert "orchestrator-state.yaml" in state.stdout


def test_resume_orchestrate_advances_done_worker_without_accepting(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    create_task(root, "Resume A", "docs/a/**")

    started = run_cli("orchestrate", "--root", str(root), "--parallel", "1")
    run_dir = next((root / ".agent-runs").iterdir())
    (root / "docs" / "a").mkdir(parents=True)
    (root / "docs" / "a" / "resume.md").write_text("# Resume\n", encoding="utf-8")
    complete = run_cli("complete", run_dir.name, "--root", str(root), "--agent-id", "worker-1")
    resumed = run_cli("resume-orchestrate", "--root", str(root), "--watch", "--timeout", "5")

    evidence = (run_dir / "orchestrate-worker.yaml").read_text(encoding="utf-8")
    assert started.returncode == 0, started.stderr
    assert complete.returncode == 0, complete.stderr
    assert resumed.returncode == 0, resumed.stderr
    assert "status: review_ready" in evidence
    assert (run_dir / "review.md").is_file()
    assert len(list((root / ".tasks" / "done").glob("*.md"))) == 0
    assert "review_ready" in (root / ".agent-loop" / "orchestrate-report.md").read_text(encoding="utf-8")


def test_resume_orchestrate_isolates_failed_worker(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    create_task(root, "Fail A", "docs/a/**")
    create_task(root, "Done B", "docs/b/**")
    fake = "python3 -c \"import os, sys; from pathlib import Path; agent=os.environ['AGENT_ID']; Path('mailbox').mkdir(exist_ok=True); (Path('mailbox')/(agent+'.done.md')).write_text('status: done\\n') if agent=='worker-2' else None; sys.exit(1 if agent=='worker-1' else 0)\""

    result = run_cli("orchestrate", "--root", str(root), "--parallel", "2", "--run-command", fake, "--watch", "--timeout", "10")
    resumed = run_cli("resume-orchestrate", "--root", str(root), "--watch", "--timeout", "5")

    report = (root / ".agent-loop" / "orchestrate-report.md").read_text(encoding="utf-8")
    state = (root / ".agent-loop" / "orchestrator-state.yaml").read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert resumed.returncode == 0, resumed.stderr
    assert "worker-1" in report and "failed" in report
    assert "worker-2" in report and "review_ready" in report
    assert "exit_code: 1" in state
    assert "exit_code: 0" in state
