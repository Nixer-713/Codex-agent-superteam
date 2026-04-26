from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .paths import resolve_paths
from .privacy import privacy_scan
from .review import create_review
from .runs import get_run
from .state_machine import resume_run
from .tasks import activate_task, create_task, first_pending, parse_task
from .template import template_init
from .dispatch import write_completion


def run_self_test() -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="agent-loop-self-test-") as temp:
        root = Path(temp) / "project"
        root.mkdir()
        git(root, "init")
        git(root, "config", "user.email", "agent-loop@example.invalid")
        git(root, "config", "user.name", "Agent Loop")
        (root / "README.md").write_text("# Self Test\n", encoding="utf-8")
        git(root, "add", "README.md")
        git(root, "commit", "-m", "initial commit")

        paths = resolve_paths(root)
        paths.ensure()
        template_init(root, github_templates=True)
        task_path = create_task(paths, "Self test docs", ["docs/**"], [], [])
        active = activate_task(paths, first_pending(paths))
        task = parse_task(active)
        from .runs import create_run

        run_dir = create_run(paths, task)
        (root / "docs").mkdir()
        (root / "docs" / "self-test.md").write_text("# Self Test\n", encoding="utf-8")
        write_completion(run_dir, "worker-1", "success", "Self-test worker completed.")
        state = resume_run(root, run_dir)
        if not (run_dir / "review.md").exists():
            create_review(run_dir)
        privacy_code, privacy_output = privacy_scan(root)
        if privacy_code != 0:
            return 1, f"Self-test failed: privacy-scan failed ({privacy_output})\n"
        if not (run_dir / "review.md").exists() or not (run_dir / "scope-check.yaml").exists():
            return 1, f"Self-test failed: missing review-ready evidence, phase {state.get('phase')}\n"
        return 0, "\n".join(
            [
                "Self-test passed",
                f"template-init: {root / '.agent-loop' / 'config.yaml'}",
                f"run evidence: {run_dir}",
                f"privacy-scan: {privacy_output}",
            ]
        ) + "\n"


def git(root: Path, *args: str) -> None:
    result = subprocess.run(["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
