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


def test_orchestrate_run_command_records_process_logs_and_exit(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    create_task(root, "Parallel A", "docs/a/**")
    create_task(root, "Parallel B", "docs/b/**")
    fake = (
        "python3 -c \"from pathlib import Path; import os; "
        "agent=os.environ['AGENT_ID']; "
        "Path('mailbox').mkdir(exist_ok=True); "
        "Path('mailbox/'+agent+'.done.md').write_text('agent_id: '+agent+'\\nstatus: done\\nsummary: ok\\n'); "
        "print('fake worker '+agent)\""
    )

    result = run_cli("orchestrate", "--root", str(root), "--parallel", "2", "--run-command", fake, "--watch", "--timeout", "30")

    assert result.returncode == 0, result.stderr
    runs = sorted((root / ".agent-runs").iterdir())
    assert len(runs) == 2
    for run_dir in runs:
        evidence = (run_dir / "orchestrate-worker.yaml").read_text(encoding="utf-8")
        assert "pid:" in evidence
        assert "exit_code: 0" in evidence
        assert "status: review_ready" in evidence
        assert "duration_seconds:" in evidence
        assert (run_dir / "worker.stdout.log").is_file()
        assert "fake worker" in (run_dir / "worker.stdout.log").read_text(encoding="utf-8")
        state = run_cli("state", run_dir.name, "--root", str(root))
        assert state.returncode == 0, state.stderr
        assert "worker_status: review_ready" in state.stdout
        final_report = run_cli("report", run_dir.name, "--root", str(root))
        assert final_report.returncode == 0, final_report.stderr
        report_text = (run_dir / "final-report.md").read_text(encoding="utf-8")
        assert "Worker Summary" in report_text
        assert "worker.stdout.log" in report_text
    report = (root / ".agent-loop" / "orchestrate-report.md").read_text(encoding="utf-8")
    assert "worker.stdout.log" in report
    assert "exit_code" in report
    assert "Next Recommended Commands" in report


def test_orchestrate_run_command_failure_is_isolated(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    create_task(root, "Fail A", "docs/a/**")
    create_task(root, "Fail B", "docs/b/**")
    fake = "python3 -c \"import os, sys; print('worker '+os.environ['AGENT_ID']); sys.exit(1 if os.environ['AGENT_ID']=='worker-1' else 0)\""

    result = run_cli("orchestrate", "--root", str(root), "--parallel", "2", "--run-command", fake, "--watch", "--timeout", "30")

    assert result.returncode == 0, result.stderr
    report = (root / ".agent-loop" / "orchestrate-report.md").read_text(encoding="utf-8")
    assert "failed" in report
    assert "worker-1" in report
    assert (root / ".agent-loop" / "orchestrate-result.yaml").is_file()
