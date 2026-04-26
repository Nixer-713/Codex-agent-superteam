import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "agent_loop.cli", *args],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_self_test_runs_core_loop_without_project_setup():
    result = run_cli("self-test")

    assert result.returncode == 0, result.stderr
    assert "Self-test passed" in result.stdout
    assert "template-init" in result.stdout
    assert "run evidence" in result.stdout
    assert "privacy-scan" in result.stdout
