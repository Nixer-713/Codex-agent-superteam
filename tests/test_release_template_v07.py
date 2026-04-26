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


def test_template_init_generates_generic_project_files(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)

    result = run_cli("template-init", "--root", str(root), "--github-templates")

    assert result.returncode == 0, result.stderr
    config = root / ".agent-loop" / "config.yaml"
    issue = root / ".github" / "ISSUE_TEMPLATE" / "codex-task.yml"
    pr_template = root / ".github" / "pull_request_template.md"
    assert config.is_file()
    assert issue.is_file()
    assert pr_template.is_file()
    combined = config.read_text(encoding="utf-8") + issue.read_text(encoding="utf-8") + pr_template.read_text(encoding="utf-8")
    assert "$PROJECT_ROOT" in combined
    assert "/Users/" not in combined
    assert ("github" + "_pat_") not in combined


def test_privacy_scan_redacts_token_excerpts(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    fake_token = "github" + "_pat_" + "1234567890abcdef"
    private_path = "/" + "Users" + "/example/private"
    secret = root / "secret.md"
    secret.write_text(f"token={fake_token}\npath={private_path}\n", encoding="utf-8")
    git(root, "add", "secret.md")

    result = run_cli("privacy-scan", "--root", str(root))

    evidence = root / ".agent-loop" / "privacy-scan.yaml"
    text = evidence.read_text(encoding="utf-8")
    assert result.returncode == 1
    assert "token" in text
    assert "absolute_path" in text
    assert fake_token not in text
    assert "***" in text


def test_release_check_writes_markdown_and_detects_version_tag_mismatch(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    (root / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "1.2.3"\n', encoding="utf-8")
    git(root, "add", "pyproject.toml")
    git(root, "commit", "-m", "package metadata")

    result = run_cli("release-check", "--root", str(root))

    yaml = root / ".agent-loop" / "release-check.yaml"
    markdown = root / ".agent-loop" / "release-check.md"
    assert result.returncode == 1
    assert yaml.is_file()
    assert markdown.is_file()
    assert "version_tag" in yaml.read_text(encoding="utf-8")
    assert "FAIL" in markdown.read_text(encoding="utf-8")
