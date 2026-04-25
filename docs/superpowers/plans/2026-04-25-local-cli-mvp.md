# Local CLI MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Python CLI that turns the Codex Agent Loop design into a runnable file/Git-backed task workflow.

**Architecture:** The CLI operates on a target project directory, creates task/run/review artifacts, snapshots Git state, builds short context packs, performs scope checks, and writes human approval gates. It does not auto-run Codex yet; it prepares bounded worker briefs so future automation can replace the manual handoff.

**Tech Stack:** Python 3.11+ standard library, `argparse`, `unittest`, Git CLI subprocesses, Markdown/YAML-like text files without third-party dependencies.

---

## File Structure

- Create `pyproject.toml`: package metadata and pytest-compatible test config.
- Create `agent_loop/__init__.py`: package version.
- Create `agent_loop/cli.py`: argparse entrypoint and command wiring.
- Create `agent_loop/paths.py`: project path resolution and directory creation.
- Create `agent_loop/tasks.py`: task creation, selection, state transitions.
- Create `agent_loop/runs.py`: run directory creation and artifact writing.
- Create `agent_loop/git_utils.py`: Git snapshots and diff collection.
- Create `agent_loop/scope_guard.py`: allowed/forbidden path matching.
- Create `agent_loop/review.py`: review artifact generation.
- Create `tests/test_cli_workflow.py`: end-to-end CLI behavior tests using temporary Git repos.

## Command MVP

- `agent-loop init [--root PATH]`: create `.tasks/`, `.agent-runs/`, `.locks/`, `.agent-loop/config.yaml`.
- `agent-loop new-task TITLE [--root PATH] [--allowed PATH ...] [--forbidden PATH ...] [--validation CMD ...]`: create pending task Markdown.
- `agent-loop run-next [--root PATH]`: pick first pending task, create run directory, snapshot Git, move task to active, create `context-pack.md` and `worker-brief.md`.
- `agent-loop capture-diff RUN_ID [--root PATH]`: write `changed-files.txt`, `diff.patch`, `diff-stat.txt`.
- `agent-loop scope-check RUN_ID [--root PATH]`: compare changed files with task scope and write `scope-check.yaml`.
- `agent-loop review RUN_ID [--root PATH]`: create `review.md` with accept/revise/split/rollback decision placeholder and checklist.
- `agent-loop status [--root PATH]`: print active/pending/done tasks and latest run state.
- `agent-loop accept RUN_ID [--root PATH] [--commit]`: move active task to done; if `--commit`, run `git add` and `git commit` using generated message.

## Task 1: CLI Skeleton And Init

**Files:**
- Create: `pyproject.toml`
- Create: `agent_loop/__init__.py`
- Create: `agent_loop/cli.py`
- Create: `agent_loop/paths.py`
- Create: `tests/test_cli_workflow.py`

- [ ] **Step 1: Write failing tests for `init`**

```python
def test_init_creates_workspace_directories(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    result = run_cli("init", "--root", str(root))
    assert result.returncode == 0
    assert (root / ".tasks" / "pending").is_dir()
    assert (root / ".tasks" / "active").is_dir()
    assert (root / ".tasks" / "done").is_dir()
    assert (root / ".agent-runs").is_dir()
    assert (root / ".locks").is_dir()
    assert (root / ".agent-loop" / "config.yaml").is_file()
```

- [ ] **Step 2: Run test and verify it fails**

Run: `python -m pytest tests/test_cli_workflow.py::test_init_creates_workspace_directories -q`
Expected: FAIL because `agent_loop` package/CLI does not exist.

- [ ] **Step 3: Implement minimal init command**

Implement `main(argv=None)`, root resolution, and directory creation.

- [ ] **Step 4: Run test and verify it passes**

Run: `python -m pytest tests/test_cli_workflow.py::test_init_creates_workspace_directories -q`
Expected: PASS.

## Task 2: Task Creation And Run Start

**Files:**
- Modify: `agent_loop/tasks.py`
- Modify: `agent_loop/runs.py`
- Modify: `agent_loop/cli.py`
- Modify: `tests/test_cli_workflow.py`

- [ ] **Step 1: Write failing test for creating and starting a task**

Test creates a Git repo, runs `new-task`, then `run-next`, and asserts task moves from pending to active and a run directory contains `input-task.md`, `before-head.txt`, `context-pack.md`, `worker-brief.md`, `status.yaml`.

- [ ] **Step 2: Verify test fails for missing commands**

Run the specific test and confirm missing implementation failure.

- [ ] **Step 3: Implement task and run store**

Create timestamped task files and run IDs, snapshot `git rev-parse HEAD` when available.

- [ ] **Step 4: Verify test passes**

Run the specific test.

## Task 3: Diff Capture And Scope Guard

**Files:**
- Create: `agent_loop/git_utils.py`
- Create: `agent_loop/scope_guard.py`
- Modify: `agent_loop/cli.py`
- Modify: `tests/test_cli_workflow.py`

- [ ] **Step 1: Write failing test for diff capture and scope violation**

Test starts a task with `--allowed src/** --forbidden secrets/**`, modifies files in both paths, runs `capture-diff` and `scope-check`, then asserts changed files and violation are written.

- [ ] **Step 2: Verify test fails**

Run the specific test.

- [ ] **Step 3: Implement Git diff capture and glob matching**

Use `git diff --name-only`, `git diff --stat`, and `git diff`; use `fnmatch.fnmatch` for scope matching.

- [ ] **Step 4: Verify test passes**

Run the specific test.

## Task 4: Review, Status, Accept

**Files:**
- Create: `agent_loop/review.py`
- Modify: `agent_loop/tasks.py`
- Modify: `agent_loop/runs.py`
- Modify: `agent_loop/cli.py`
- Modify: `tests/test_cli_workflow.py`

- [ ] **Step 1: Write failing test for review/status/accept**

Test generates review file, prints status, accepts run without commit, and asserts task moves to done and status reports no active task.

- [ ] **Step 2: Verify test fails**

Run the specific test.

- [ ] **Step 3: Implement review/status/accept**

Generate review checklist, update status, move task file active to done. Implement optional commit but keep tests on non-commit path.

- [ ] **Step 4: Verify test passes**

Run the specific test.

## Task 5: Final Verification

**Files:**
- Modify docs only if CLI usage differs from plan.

- [ ] Run: `python -m pytest -q`
- [ ] Run: `python -m agent_loop.cli --help`
- [ ] Run a manual smoke flow in a temporary Git repo.
- [ ] Update `README.md` with basic usage commands.
