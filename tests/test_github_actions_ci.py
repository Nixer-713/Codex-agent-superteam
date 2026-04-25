from pathlib import Path


def test_github_actions_ci_runs_pytest_on_push_and_pr():
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "test.yml"

    text = workflow.read_text(encoding="utf-8")

    assert "pull_request:" in text
    assert "push:" in text
    assert "actions/checkout" in text
    assert "actions/setup-python" in text
    assert "python3 -m pytest -q" in text
