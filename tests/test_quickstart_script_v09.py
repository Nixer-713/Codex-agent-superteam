import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "agent-loop-quickstart.sh"


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


def run_script(*args):
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=PROJECT_ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_quickstart_init_only_generates_config_and_doctor(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)

    result = run_script("--root", str(root), "--init-only")

    assert result.returncode == 0, result.stderr
    assert "Quickstart complete" in result.stdout
    assert (root / ".agent-loop" / "config.yaml").is_file()
    assert (root / ".github" / "pull_request_template.md").is_file()
    assert not list((root / ".tasks" / "pending").glob("*.md"))


def test_quickstart_task_starts_orchestration_without_accepting(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)

    result = run_script("--root", str(root), "--task", "Add docs", "--allowed", "docs/**", "--parallel", "1")

    assert result.returncode == 0, result.stderr
    assert "Human gate" in result.stdout
    assert list((root / ".agent-runs").iterdir())
    assert list((root / ".tasks" / "active").glob("*.md"))
    assert not list((root / ".tasks" / "done").glob("*.md"))
