from __future__ import annotations

from pathlib import Path


def create_review(run_dir: Path) -> Path:
    changed = read_optional(run_dir / "changed-files.txt") or "<capture-diff has not been run>\n"
    scope = read_optional(run_dir / "scope-check.yaml") or "<scope-check has not been run>\n"
    review_path = run_dir / "review.md"
    review_path.write_text(
        f"""# Review Report

## Decision

accept | revise | split | rollback | escalate

## Changed Files

```text
{changed.rstrip()}
```

## Scope Check

```yaml
{scope.rstrip()}
```

## Blocking Findings

- [ ] No scope violations remain.
- [ ] Acceptance criteria are satisfied.
- [ ] Validation commands were run or explicitly waived by a human.
- [ ] Patch size is appropriate for this task.

## Required Next Action

Choose one decision above. Use `agent-loop accept <run-id>` only after review approval.
""",
        encoding="utf-8",
    )
    return review_path


def read_optional(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""
