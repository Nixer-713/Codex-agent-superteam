import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "agent-loop-wizard.sh"


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


def run_wizard(input_text: str):
    return subprocess.run(["bash", str(SCRIPT)], cwd=PROJECT_ROOT, input=input_text, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_wizard_collects_required_fields_and_starts_task(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    answers = "\n".join([
        str(root),
        "Demo project",
        "Add docs smoke page",
        "docs/**",
        "",
        "",
        "1",
        "n",
        "n",
        "strict",
        "y",
    ]) + "\n"

    result = run_wizard(answers)

    assert result.returncode == 0, result.stderr
    assert "Wizard complete" in result.stdout
    assert "Review policy: strict" in result.stdout
    assert (root / ".agent-loop" / "config.yaml").is_file()
    assert list((root / ".agent-runs").iterdir())
    assert list((root / ".tasks" / "active").glob("*.md"))
    assert not list((root / ".tasks" / "done").glob("*.md"))


def test_wizard_declines_before_start_without_mutating(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    answers = "\n".join([
        str(root),
        "Demo project",
        "Add docs smoke page",
        "docs/**",
        "",
        "",
        "1",
        "n",
        "n",
        "smart",
        "n",
    ]) + "\n"

    result = run_wizard(answers)

    assert result.returncode == 0, result.stderr
    assert "Cancelled before orchestration" in result.stdout
    assert (root / ".agent-loop" / "config.yaml").is_file()
    assert not (root / ".agent-runs").exists() or not list((root / ".agent-runs").iterdir())


def test_wizard_prompts_include_chinese_parentheses(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    answers = "\n".join([
        str(root),
        "Demo project",
        "Add docs smoke page",
        "docs/**",
        "",
        "",
        "1",
        "n",
        "n",
        "strict",
        "n",
    ]) + "\n"

    result = run_wizard(answers)

    assert result.returncode == 0, result.stderr
    assert "Project root path（项目根目录路径）" in result.stderr
    assert "Task / requirement to implement（要实现的任务或需求）" in result.stderr
    assert "Review policy: strict | smart | auto（审核策略" in result.stderr
