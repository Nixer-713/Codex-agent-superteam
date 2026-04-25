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
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stderr
    return result


def init_git_repo(root: Path):
    git(root, "init")
    git(root, "config", "user.email", "codex-agent-loop@example.local")
    git(root, "config", "user.name", "Codex Agent Loop")
    (root / "README.md").write_text("# Repo\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "initial commit")


def test_init_creates_workspace_directories(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()

    result = run_cli("init", "--root", str(root))

    assert result.returncode == 0, result.stderr
    assert (root / ".tasks" / "pending").is_dir()
    assert (root / ".tasks" / "active").is_dir()
    assert (root / ".tasks" / "done").is_dir()
    assert (root / ".agent-runs").is_dir()
    assert (root / ".locks").is_dir()
    assert (root / ".agent-loop" / "config.yaml").is_file()


def test_placeholder_root_gets_friendly_error():
    result = run_cli("init", "--root", "/path/to/project")

    assert result.returncode == 2
    assert "placeholder" in result.stderr
    assert "/path/to/project" in result.stderr


def test_new_task_and_run_next_create_bounded_worker_brief(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0

    created = run_cli(
        "new-task",
        "Add login validation",
        "--root",
        str(root),
        "--allowed",
        "src/auth/**",
        "--forbidden",
        "infra/**",
        "--validation",
        "python -m pytest",
    )
    assert created.returncode == 0, created.stderr
    pending = list((root / ".tasks" / "pending").glob("*.md"))
    assert len(pending) == 1
    assert "Add login validation" in pending[0].read_text(encoding="utf-8")

    started = run_cli("run-next", "--root", str(root))

    assert started.returncode == 0, started.stderr
    active = list((root / ".tasks" / "active").glob("*.md"))
    assert len(active) == 1
    runs = list((root / ".agent-runs").iterdir())
    assert len(runs) == 1
    run_dir = runs[0]
    assert (run_dir / "input-task.md").is_file()
    assert (run_dir / "before-head.txt").read_text(encoding="utf-8").strip()
    assert "Add login validation" in (run_dir / "context-pack.md").read_text(encoding="utf-8")
    worker_brief = (run_dir / "worker-brief.md").read_text(encoding="utf-8")
    assert "src/auth/**" in worker_brief
    assert "infra/**" in worker_brief
    assert "status: running" in (run_dir / "status.yaml").read_text(encoding="utf-8")


def test_capture_diff_and_scope_check_detect_scope_violation(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli(
        "new-task",
        "Change auth only",
        "--root",
        str(root),
        "--allowed",
        "src/**",
        "--forbidden",
        "secrets/**",
    ).returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]

    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "secrets").mkdir()
    (root / "secrets" / "token.txt").write_text("secret\n", encoding="utf-8")

    captured = run_cli("capture-diff", run_id, "--root", str(root))
    checked = run_cli("scope-check", run_id, "--root", str(root))

    assert captured.returncode == 0, captured.stderr
    assert checked.returncode == 2
    run_dir = root / ".agent-runs" / run_id
    changed_files = (run_dir / "changed-files.txt").read_text(encoding="utf-8")
    assert "src/app.py" in changed_files
    assert "secrets/token.txt" in changed_files
    scope_report = (run_dir / "scope-check.yaml").read_text(encoding="utf-8")
    assert "status: violation" in scope_report
    assert "secrets/token.txt" in scope_report


def test_review_status_and_accept_move_task_to_done(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Document flow", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]
    (root / "docs").mkdir()
    (root / "docs" / "flow.md").write_text("# Flow\n", encoding="utf-8")
    assert run_cli("capture-diff", run_id, "--root", str(root)).returncode == 0
    assert run_cli("scope-check", run_id, "--root", str(root)).returncode == 0

    reviewed = run_cli("review", run_id, "--root", str(root))
    before_status = run_cli("status", "--root", str(root))
    accepted = run_cli("accept", run_id, "--root", str(root))
    after_status = run_cli("status", "--root", str(root))

    assert reviewed.returncode == 0, reviewed.stderr
    assert "Decision" in (root / ".agent-runs" / run_id / "review.md").read_text(encoding="utf-8")
    assert before_status.returncode == 0
    assert "active: 1" in before_status.stdout
    assert accepted.returncode == 0, accepted.stderr
    assert len(list((root / ".tasks" / "active").glob("*.md"))) == 0
    assert len(list((root / ".tasks" / "done").glob("*.md"))) == 1
    assert "active: 0" in after_status.stdout


def test_accept_commit_is_idempotent_after_plain_accept(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Document flow", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]
    (root / "docs").mkdir()
    (root / "docs" / "flow.md").write_text("# Flow\n", encoding="utf-8")
    assert run_cli("capture-diff", run_id, "--root", str(root)).returncode == 0
    assert run_cli("scope-check", run_id, "--root", str(root)).returncode == 0
    assert run_cli("review", run_id, "--root", str(root)).returncode == 0
    assert run_cli("accept", run_id, "--root", str(root)).returncode == 0

    committed = run_cli("accept", run_id, "--root", str(root), "--commit")

    assert committed.returncode == 0, committed.stderr
    log = git(root, "log", "--oneline", "-1").stdout
    assert "accept" in log
    assert len(list((root / ".tasks" / "active").glob("*.md"))) == 0
    assert len(list((root / ".tasks" / "done").glob("*.md"))) == 1


def test_dispatch_writes_codex_worker_prompt(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli(
        "new-task",
        "Add auth helper",
        "--root",
        str(root),
        "--allowed",
        "src/auth/**",
        "--forbidden",
        "infra/**",
    ).returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]

    dispatched = run_cli("dispatch", run_id, "--root", str(root), "--agent-id", "worker-auth")

    assert dispatched.returncode == 0, dispatched.stderr
    prompt_path = root / ".agent-runs" / run_id / "worker-auth.prompt.md"
    assert prompt_path.is_file()
    prompt = prompt_path.read_text(encoding="utf-8")
    assert "You are a bounded Codex worker" in prompt
    assert "Karpathy Coding Guidelines" in prompt
    assert "protocols/execution-protocol.md" in prompt
    assert "src/auth/**" in prompt
    assert "infra/**" in prompt
    assert "mailbox/worker-auth.done.md" in prompt


def test_complete_writes_done_signal_and_summary(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Document flow", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]

    completed = run_cli(
        "complete",
        run_id,
        "--root",
        str(root),
        "--agent-id",
        "worker-docs",
        "--result",
        "success",
        "--message",
        "Added docs flow.",
    )

    assert completed.returncode == 0, completed.stderr
    run_dir = root / ".agent-runs" / run_id
    done_file = run_dir / "mailbox" / "worker-docs.done.md"
    assert done_file.is_file()
    done_text = done_file.read_text(encoding="utf-8")
    assert "agent_id: worker-docs" in done_text
    assert "result: success" in done_text
    assert "Added docs flow." in done_text
    assert "worker-docs: done" in (run_dir / "status.yaml").read_text(encoding="utf-8")


def test_advance_waits_for_done_signal_then_reviews(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Document flow", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]
    (root / "docs").mkdir()
    (root / "docs" / "flow.md").write_text("# Flow\n", encoding="utf-8")
    assert run_cli(
        "complete",
        run_id,
        "--root",
        str(root),
        "--agent-id",
        "worker-docs",
        "--message",
        "Done.",
    ).returncode == 0

    advanced = run_cli("advance", run_id, "--root", str(root), "--agent-id", "worker-docs")

    assert advanced.returncode == 0, advanced.stderr
    run_dir = root / ".agent-runs" / run_id
    assert "docs/flow.md" in (run_dir / "changed-files.txt").read_text(encoding="utf-8")
    assert "status: ok" in (run_dir / "scope-check.yaml").read_text(encoding="utf-8")
    assert (run_dir / "review.md").is_file()
    assert "review_ready" in (run_dir / "status.yaml").read_text(encoding="utf-8")


def test_advance_returns_blocked_when_done_signal_missing(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Document flow", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]

    advanced = run_cli("advance", run_id, "--root", str(root), "--agent-id", "worker-docs")

    assert advanced.returncode == 3
    assert "missing done signal" in advanced.stderr


def test_doctor_reports_healthy_initialized_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0

    result = run_cli("doctor", "--root", str(root))

    assert result.returncode == 0, result.stderr
    assert "Codex Agent Loop Doctor" in result.stdout
    assert "[OK] git.repository" in result.stdout
    assert "[OK] workspace.directories" in result.stdout
    assert "FAIL: 0" in result.stdout


def test_doctor_fails_for_missing_workspace(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)

    result = run_cli("doctor", "--root", str(root))

    assert result.returncode == 1
    assert "[FAIL] workspace.directories" in result.stdout
    assert "agent-loop init" in result.stdout


def test_new_task_requires_git_repository(tmp_path):
    root = tmp_path / "not-git"
    root.mkdir()

    result = run_cli("new-task", "Should fail", "--root", str(root), "--allowed", "docs/**")

    assert result.returncode == 2
    assert "not a Git repository" in result.stderr


def test_accept_requires_git_repository_before_state_change(tmp_path):
    root = tmp_path / "not-git"
    root.mkdir()
    assert run_cli("init", "--root", str(root)).returncode == 0
    run_dir = root / ".agent-runs" / "run-test"
    run_dir.mkdir(parents=True)
    (run_dir / "status.yaml").write_text("run_id: run-test\ntask_id: task-test\nstatus: running\n", encoding="utf-8")

    result = run_cli("accept", "run-test", "--root", str(root), "--commit")

    assert result.returncode == 2
    assert "not a Git repository" in result.stderr


def test_blocked_writes_blocked_signal(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Needs decision", "--root", str(root), "--allowed", "src/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]

    blocked = run_cli(
        "blocked",
        run_id,
        "--root",
        str(root),
        "--agent-id",
        "worker-1",
        "--reason",
        "Need to change forbidden path.",
    )

    assert blocked.returncode == 0, blocked.stderr
    blocked_file = root / ".agent-runs" / run_id / "mailbox" / "worker-1.blocked.md"
    assert blocked_file.is_file()
    assert "Need to change forbidden path." in blocked_file.read_text(encoding="utf-8")


def test_watch_advances_when_done_signal_exists(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Document flow", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]
    (root / "docs").mkdir()
    (root / "docs" / "flow.md").write_text("# Flow\n", encoding="utf-8")
    assert run_cli("complete", run_id, "--root", str(root), "--agent-id", "worker-1").returncode == 0

    watched = run_cli("watch", run_id, "--root", str(root), "--agent-id", "worker-1", "--timeout", "0")

    assert watched.returncode == 0, watched.stderr
    assert "review_ready" in watched.stdout
    run_dir = root / ".agent-runs" / run_id
    assert (run_dir / "review.md").is_file()
    assert "phase: review_ready" in (run_dir / "status.yaml").read_text(encoding="utf-8")


def test_watch_stops_when_blocked_signal_exists(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Needs decision", "--root", str(root), "--allowed", "src/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]
    assert run_cli("blocked", run_id, "--root", str(root), "--agent-id", "worker-1", "--reason", "Need decision").returncode == 0

    watched = run_cli("watch", run_id, "--root", str(root), "--agent-id", "worker-1", "--timeout", "0")

    assert watched.returncode == 4
    assert "blocked" in watched.stderr


def test_dispatch_can_write_codex_exec_command_without_running_it(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Add helper", "--root", str(root), "--allowed", "src/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]

    dispatched = run_cli("dispatch", run_id, "--root", str(root), "--agent-id", "worker-1", "--codex-command")

    assert dispatched.returncode == 0, dispatched.stderr
    command_file = root / ".agent-runs" / run_id / "worker-1.codex-command.sh"
    assert command_file.is_file()
    command = command_file.read_text(encoding="utf-8")
    assert "codex exec" in command
    assert "--cd" in command
    assert "--ask-for-approval" not in command
    assert "worker-1.prompt.md" in command


def test_run_codex_dry_run_writes_intended_command(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Add helper", "--root", str(root), "--allowed", "src/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]
    assert run_cli("dispatch", run_id, "--root", str(root), "--agent-id", "worker-1").returncode == 0

    result = run_cli("run-codex", run_id, "--root", str(root), "--agent-id", "worker-1", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "codex exec" in result.stdout
    run_dir = root / ".agent-runs" / run_id
    assert (run_dir / "worker-1.codex-command.sh").is_file()
    assert (run_dir / "worker-1.codex-output.txt").exists() is False


def test_worktree_start_creates_branch_and_records_assignment(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Parallel docs", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]
    worktree_dir = tmp_path / "worker-docs-tree"

    result = run_cli(
        "worktree-start",
        run_id,
        "--root",
        str(root),
        "--agent-id",
        "worker-docs",
        "--path",
        str(worktree_dir),
    )

    assert result.returncode == 0, result.stderr
    assert worktree_dir.is_dir()
    assert (worktree_dir / ".git").exists()
    status = (root / ".agent-runs" / run_id / "worktrees.yaml").read_text(encoding="utf-8")
    assert "worker-docs" in status
    assert "codex/" in status
    branches = git(root, "branch", "--list", "codex/*").stdout
    assert "worker-docs" in branches


def test_watch_collects_done_signal_from_worktree(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Parallel docs", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]
    worktree_dir = tmp_path / "worker-docs-tree"
    assert run_cli("worktree-start", run_id, "--root", str(root), "--agent-id", "worker-docs", "--path", str(worktree_dir)).returncode == 0
    (worktree_dir / "docs").mkdir(exist_ok=True)
    (worktree_dir / "docs" / "parallel.md").write_text("# Parallel\n", encoding="utf-8")
    (worktree_dir / "mailbox").mkdir()
    (worktree_dir / "mailbox" / "worker-docs.done.md").write_text("agent_id: worker-docs\nstatus: done\n", encoding="utf-8")

    watched = run_cli("watch", run_id, "--root", str(root), "--agent-id", "worker-docs", "--timeout", "0")

    assert watched.returncode == 0, watched.stderr
    run_dir = root / ".agent-runs" / run_id
    assert (run_dir / "mailbox" / "worker-docs.done.md").is_file()
    assert "docs/parallel.md" in (run_dir / "changed-files.txt").read_text(encoding="utf-8")
    assert "status: ok" in (run_dir / "scope-check.yaml").read_text(encoding="utf-8")


def test_auto_next_dispatch_only_starts_next_task(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Auto docs", "--root", str(root), "--allowed", "docs/**").returncode == 0

    result = run_cli("auto-next", "--root", str(root), "--agent-id", "worker-auto")

    assert result.returncode == 0, result.stderr
    assert "started" in result.stdout
    assert "dispatched" in result.stdout
    runs = list((root / ".agent-runs").iterdir())
    assert len(runs) == 1
    run_dir = runs[0]
    assert (run_dir / "worker-auto.prompt.md").is_file()
    assert len(list((root / ".tasks" / "active").glob("*.md"))) == 1


def test_auto_next_with_watch_requires_done_signal(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Auto docs", "--root", str(root), "--allowed", "docs/**").returncode == 0

    result = run_cli("auto-next", "--root", str(root), "--agent-id", "worker-auto", "--watch", "--watch-timeout", "0")

    assert result.returncode == 3
    assert "timeout waiting for done signal" in result.stderr


def test_auto_next_can_create_worker_worktree(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Parallel auto docs", "--root", str(root), "--allowed", "docs/**").returncode == 0
    worktree_dir = tmp_path / "auto-worker-tree"

    result = run_cli(
        "auto-next",
        "--root",
        str(root),
        "--agent-id",
        "worker-auto",
        "--worktree",
        "--worktree-path",
        str(worktree_dir),
        "--codex-command",
    )

    assert result.returncode == 0, result.stderr
    assert worktree_dir.is_dir()
    assert "worktree" in result.stdout
    runs = list((root / ".agent-runs").iterdir())
    assert len(runs) == 1
    run_dir = runs[0]
    assert (run_dir / "worktrees.yaml").is_file()
    command = (run_dir / "worker-auto.codex-command.sh").read_text(encoding="utf-8")
    assert str(worktree_dir) in command


def prepare_worktree_done(root: Path, tmp_path: Path):
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Merge docs", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]
    worktree_dir = tmp_path / "merge-worker-tree"
    assert run_cli("worktree-start", run_id, "--root", str(root), "--agent-id", "worker-docs", "--path", str(worktree_dir)).returncode == 0
    (worktree_dir / "docs").mkdir(exist_ok=True)
    (worktree_dir / "docs" / "merge-doc.md").write_text("# Merge Doc\n", encoding="utf-8")
    (worktree_dir / "mailbox").mkdir()
    (worktree_dir / "mailbox" / "worker-docs.done.md").write_text(
        "agent_id: worker-docs\nstatus: done\nchanged_files:\n  - docs/merge-doc.md\nsummary: done\n",
        encoding="utf-8",
    )
    return run_id, worktree_dir


def test_merge_preflight_requires_done_signal(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "Merge docs", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    run_id = started.stdout.strip().split()[-1]
    worktree_dir = tmp_path / "merge-worker-tree"
    assert run_cli("worktree-start", run_id, "--root", str(root), "--agent-id", "worker-docs", "--path", str(worktree_dir)).returncode == 0

    result = run_cli("merge-preflight", run_id, "--root", str(root), "--agent-id", "worker-docs")

    assert result.returncode == 1
    report = (root / ".agent-runs" / run_id / "merge-preflight.yaml").read_text(encoding="utf-8")
    assert "status: fail" in report
    assert "done_signal: missing" in report


def test_worktree_preview_generates_evidence_bundle(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    run_id, _ = prepare_worktree_done(root, tmp_path)

    assert run_cli("worktree-collect", run_id, "--root", str(root), "--agent-id", "worker-docs").returncode == 0
    assert run_cli("merge-preflight", run_id, "--root", str(root), "--agent-id", "worker-docs").returncode == 0
    result = run_cli("worktree-preview", run_id, "--root", str(root), "--agent-id", "worker-docs")

    assert result.returncode == 0, result.stderr
    run_dir = root / ".agent-runs" / run_id
    for name in ["changed-files.txt", "diff-stat.txt", "diff.patch", "scope-check.yaml", "risk.yaml", "validation.yaml", "review.md"]:
        assert (run_dir / name).is_file(), name
    assert "status: ok" in (run_dir / "scope-check.yaml").read_text(encoding="utf-8")
    assert "risk: low" in (run_dir / "risk.yaml").read_text(encoding="utf-8")
    assert "decision: needs_human_decision" in (run_dir / "review.md").read_text(encoding="utf-8")


def test_worktree_apply_requires_review_accept(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    run_id, _ = prepare_worktree_done(root, tmp_path)
    assert run_cli("worktree-collect", run_id, "--root", str(root), "--agent-id", "worker-docs").returncode == 0
    assert run_cli("merge-preflight", run_id, "--root", str(root), "--agent-id", "worker-docs").returncode == 0
    assert run_cli("worktree-preview", run_id, "--root", str(root), "--agent-id", "worker-docs").returncode == 0

    result = run_cli("worktree-apply", run_id, "--root", str(root), "--agent-id", "worker-docs")

    assert result.returncode == 1
    assert "review-decision" in result.stderr


def test_worktree_apply_after_review_accept_creates_merge_result(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    run_id, _ = prepare_worktree_done(root, tmp_path)
    assert run_cli("worktree-collect", run_id, "--root", str(root), "--agent-id", "worker-docs").returncode == 0
    assert run_cli("merge-preflight", run_id, "--root", str(root), "--agent-id", "worker-docs").returncode == 0
    assert run_cli("worktree-preview", run_id, "--root", str(root), "--agent-id", "worker-docs").returncode == 0
    assert run_cli("review-accept", run_id, "--root", str(root), "--agent-id", "worker-docs").returncode == 0

    result = run_cli("worktree-apply", run_id, "--root", str(root), "--agent-id", "worker-docs")

    assert result.returncode == 0, result.stderr
    assert (root / "docs" / "merge-doc.md").is_file()
    run_dir = root / ".agent-runs" / run_id
    assert "match: true" in (run_dir / "merge-result.yaml").read_text(encoding="utf-8")
    assert "phase: merge_ready" in (run_dir / "status.yaml").read_text(encoding="utf-8")


def test_accept_commit_blocks_worktree_run_until_merge_ready(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    run_id, _ = prepare_worktree_done(root, tmp_path)

    result = run_cli("accept", run_id, "--root", str(root), "--commit")

    assert result.returncode == 1
    assert "merge_ready" in result.stderr


def test_doctor_reports_worktree_evidence_gap(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    run_id, _ = prepare_worktree_done(root, tmp_path)
    assert run_cli("watch", run_id, "--root", str(root), "--agent-id", "worker-docs", "--timeout", "0").returncode == 0

    result = run_cli("doctor", "--root", str(root))

    assert result.returncode == 0
    assert "worktree_evidence" in result.stdout
    assert "worktree-collect" in result.stdout


def test_github_doctor_reports_missing_remote(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)

    result = run_cli("github-doctor", "--root", str(root))

    assert result.returncode == 1
    assert "GitHub Doctor" in result.stdout
    assert "[FAIL] github.remote" in result.stdout


def test_github_pr_body_generates_evidence_markdown(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "GitHub body docs", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip().split()[-1]
    (root / "docs").mkdir()
    (root / "docs" / "github-body.md").write_text("# GitHub Body\n", encoding="utf-8")
    assert run_cli("complete", run_id, "--root", str(root), "--agent-id", "worker-1").returncode == 0
    assert run_cli("watch", run_id, "--root", str(root), "--agent-id", "worker-1", "--timeout", "0").returncode == 0

    result = run_cli("github-pr-body", run_id, "--root", str(root))

    assert result.returncode == 0, result.stderr
    body = root / ".agent-runs" / run_id / "github-pr-body.md"
    assert body.is_file()
    text = body.read_text(encoding="utf-8")
    assert "GitHub Body" in text
    assert "Run ID" in text
    assert "docs/github-body.md" in text
    assert "scope-check.yaml" in text


def test_github_pr_create_dry_run_blocks_default_branch(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    git(root, "remote", "add", "origin", "https://github.com/Nixer-713/Codex-agent-superteam.git")
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "GitHub dry run", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    run_id = started.stdout.strip().split()[-1]
    (root / "docs").mkdir()
    (root / "docs" / "github-dry.md").write_text("# GitHub Dry\n", encoding="utf-8")
    assert run_cli("complete", run_id, "--root", str(root), "--agent-id", "worker-1").returncode == 0
    assert run_cli("watch", run_id, "--root", str(root), "--agent-id", "worker-1", "--timeout", "0").returncode == 0

    result = run_cli("github-pr-create", run_id, "--root", str(root), "--dry-run")

    assert result.returncode == 1
    assert "default branch" in result.stderr


def test_github_pr_create_dry_run_outputs_commands_on_feature_branch(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    git(root, "checkout", "-b", "codex/github-smoke")
    git(root, "remote", "add", "origin", "https://github.com/Nixer-713/Codex-agent-superteam.git")
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "GitHub dry run", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    run_id = started.stdout.strip().split()[-1]
    (root / "docs").mkdir()
    (root / "docs" / "github-dry.md").write_text("# GitHub Dry\n", encoding="utf-8")
    assert run_cli("complete", run_id, "--root", str(root), "--agent-id", "worker-1").returncode == 0
    assert run_cli("watch", run_id, "--root", str(root), "--agent-id", "worker-1", "--timeout", "0").returncode == 0
    assert run_cli("accept", run_id, "--root", str(root), "--commit").returncode == 0

    result = run_cli("github-pr-create", run_id, "--root", str(root), "--dry-run", "--draft")

    assert result.returncode == 0, result.stderr
    assert "git push" in result.stdout
    assert "gh pr create" in result.stdout
    assert "--draft" in result.stdout


def test_github_pr_create_uses_origin_default_branch_for_ahead_check(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    git(root, "branch", "-m", "trunk")
    git(root, "checkout", "-b", "codex/github-trunk")
    git(root, "remote", "add", "origin", str(root))
    git(root, "update-ref", "refs/remotes/origin/trunk", "trunk")
    git(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "GitHub trunk", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    run_id = started.stdout.strip().split()[-1]
    (root / "docs").mkdir()
    (root / "docs" / "github-trunk.md").write_text("# GitHub Trunk\n", encoding="utf-8")
    assert run_cli("complete", run_id, "--root", str(root), "--agent-id", "worker-1").returncode == 0
    assert run_cli("watch", run_id, "--root", str(root), "--agent-id", "worker-1", "--timeout", "0").returncode == 0
    assert run_cli("accept", run_id, "--root", str(root), "--commit").returncode == 0

    result = run_cli("github-pr-create", run_id, "--root", str(root), "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "gh pr create" in result.stdout


def test_github_pr_create_dry_run_requires_branch_commit(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    git(root, "checkout", "-b", "codex/no-commit")
    git(root, "remote", "add", "origin", "https://github.com/Nixer-713/Codex-agent-superteam.git")
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "GitHub no commit", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    run_id = started.stdout.strip().split()[-1]
    (root / "docs").mkdir()
    (root / "docs" / "github-no-commit.md").write_text("# No Commit\n", encoding="utf-8")
    assert run_cli("complete", run_id, "--root", str(root), "--agent-id", "worker-1").returncode == 0
    assert run_cli("watch", run_id, "--root", str(root), "--agent-id", "worker-1", "--timeout", "0").returncode == 0

    result = run_cli("github-pr-create", run_id, "--root", str(root), "--dry-run", "--draft")

    assert result.returncode == 1
    assert "no commits ahead" in result.stderr


def test_github_pr_sync_dry_run_outputs_edit_command(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    git(root, "checkout", "-b", "codex/github-sync")
    git(root, "remote", "add", "origin", "https://github.com/Nixer-713/Codex-agent-superteam.git")
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "GitHub sync", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    run_id = started.stdout.strip().split()[-1]
    (root / "docs").mkdir()
    (root / "docs" / "github-sync.md").write_text("# GitHub Sync\n", encoding="utf-8")
    assert run_cli("complete", run_id, "--root", str(root), "--agent-id", "worker-1").returncode == 0
    assert run_cli("watch", run_id, "--root", str(root), "--agent-id", "worker-1", "--timeout", "0").returncode == 0

    result = run_cli("github-pr-sync", run_id, "--root", str(root), "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "gh pr edit" in result.stdout
    assert "--body-file" in result.stdout
    assert "github-pr-body.md" in result.stdout


def test_github_pr_sync_requires_evidence(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    init_git_repo(root)
    git(root, "checkout", "-b", "codex/github-sync-missing")
    git(root, "remote", "add", "origin", "https://github.com/Nixer-713/Codex-agent-superteam.git")
    assert run_cli("init", "--root", str(root)).returncode == 0
    assert run_cli("new-task", "GitHub sync missing", "--root", str(root), "--allowed", "docs/**").returncode == 0
    started = run_cli("run-next", "--root", str(root))
    run_id = started.stdout.strip().split()[-1]

    result = run_cli("github-pr-sync", run_id, "--root", str(root), "--dry-run")

    assert result.returncode == 1
    assert "missing PR evidence" in result.stderr
