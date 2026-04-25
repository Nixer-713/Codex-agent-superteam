from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from . import git_utils
from .advance import MissingDoneSignal, ScopeViolation, advance_run
from .auto_next import AutoNextError, auto_next
from .codex_runner import run_codex_worker
from .dispatch import create_codex_command, create_worker_prompt, write_completion
from .config import load_config
from .doctor import has_failures, render_report, run_doctor
from .github_issues import import_issue, issue_comment_command, write_issue_comment, write_pr_comments
from .github_integration import (
    github_doctor,
    github_has_failures,
    github_ci_watch,
    github_pr_check,
    github_pr_create,
    github_pr_sync,
    pr_body,
    render_github_doctor,
)
from .merge_gate import (
    MergeGateError,
    apply_worktree,
    collect_worktree,
    is_merge_ready,
    is_worktree_run,
    merge_preflight,
    preview_worktree,
    review_accept,
)
from .orchestrator import orchestrate
from .paths import resolve_paths
from .privacy import privacy_scan
from .reporting import create_final_report
from .review import create_review
from .review_loop import create_revise_prompt, decision_blocks_accept, write_review_result
from .runs import create_run, get_run, run_task_id
from .scope_guard import check_scope, write_scope_report
from .state_machine import resume_run, run_state
from .tasks import activate_task, complete_active_task, create_task, first_pending, parse_task
from .watch import WatchTimeout, WorkerBlocked, watch_run, write_blocked
from .worktree import start_worktree


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-loop")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Initialize local agent-loop directories")
    add_root(init)

    new_task = subparsers.add_parser("new-task", help="Create a pending task")
    new_task.add_argument("title")
    add_root(new_task)
    new_task.add_argument("--allowed", action="append", default=[])
    new_task.add_argument("--forbidden", action="append", default=[])
    new_task.add_argument("--validation", action="append", default=[])

    run_next = subparsers.add_parser("run-next", help="Start the next pending task")
    add_root(run_next)

    capture = subparsers.add_parser("capture-diff", help="Capture current Git diff into a run")
    capture.add_argument("run_id")
    add_root(capture)

    scope = subparsers.add_parser("scope-check", help="Check changed files against task scope")
    scope.add_argument("run_id")
    add_root(scope)

    review = subparsers.add_parser("review", help="Create a review report for a run")
    review.add_argument("run_id")
    add_root(review)

    review_result = subparsers.add_parser("review-result", help="Record a review decision for a run")
    review_result.add_argument("run_id")
    review_result.add_argument("--decision", required=True, choices=["accept", "revise", "split", "rollback", "escalate"])
    review_result.add_argument("--reason", required=True)
    add_root(review_result)

    revise = subparsers.add_parser("revise", help="Create a revision worker prompt from review findings")
    revise.add_argument("run_id")
    revise.add_argument("--agent-id", default="worker-1")
    add_root(revise)

    status = subparsers.add_parser("status", help="Print task/run status")
    add_root(status)

    state = subparsers.add_parser("state", help="Show resumable run phase and missing evidence")
    state.add_argument("run_id")
    add_root(state)

    resume = subparsers.add_parser("resume", help="Resume safe mechanical evidence generation for a run")
    resume.add_argument("run_id")
    add_root(resume)

    doctor = subparsers.add_parser("doctor", help="Diagnose project readiness and workflow state")
    add_root(doctor)

    github_doctor_parser = subparsers.add_parser("github-doctor", help="Diagnose GitHub CLI and remote readiness")
    add_root(github_doctor_parser)

    dispatch = subparsers.add_parser("dispatch", help="Create a bounded Codex worker prompt")
    dispatch.add_argument("run_id")
    dispatch.add_argument("--agent-id", default="worker-1")
    dispatch.add_argument("--codex-command", action="store_true", help="Also write a codex exec shell command")
    add_root(dispatch)

    blocked = subparsers.add_parser("blocked", help="Write a worker blocked signal")
    blocked.add_argument("run_id")
    blocked.add_argument("--agent-id", default="worker-1")
    blocked.add_argument("--reason", required=True)
    add_root(blocked)

    complete = subparsers.add_parser("complete", help="Write a worker completion signal")
    complete.add_argument("run_id")
    complete.add_argument("--agent-id", default="worker-1")
    complete.add_argument("--result", default="success")
    complete.add_argument("--message", default="Worker completed the assigned task.")
    add_root(complete)

    advance = subparsers.add_parser("advance", help="Advance a completed worker run to review-ready")
    advance.add_argument("run_id")
    advance.add_argument("--agent-id", default="worker-1")
    add_root(advance)

    watch = subparsers.add_parser("watch", help="Wait for done/blocked signal, then advance to review-ready")
    watch.add_argument("run_id")
    watch.add_argument("--agent-id", default="worker-1")
    watch.add_argument("--timeout", type=float, default=300.0)
    watch.add_argument("--poll", type=float, default=2.0)
    add_root(watch)

    run_codex = subparsers.add_parser("run-codex", help="Run or preview codex exec for a worker prompt")
    run_codex.add_argument("run_id")
    run_codex.add_argument("--agent-id", default="worker-1")
    run_codex.add_argument("--dry-run", action="store_true")
    run_codex.add_argument("--timeout", type=int, default=1800)
    add_root(run_codex)

    worktree_start = subparsers.add_parser("worktree-start", help="Create an isolated git worktree for a worker")
    worktree_start.add_argument("run_id")
    worktree_start.add_argument("--agent-id", default="worker-1")
    worktree_start.add_argument("--path", default=None)
    add_root(worktree_start)

    worktree_collect = subparsers.add_parser("worktree-collect", help="Collect worktree evidence into the main run")
    worktree_collect.add_argument("run_id")
    worktree_collect.add_argument("--agent-id", default="worker-1")
    add_root(worktree_collect)

    merge_preflight_parser = subparsers.add_parser("merge-preflight", help="Check worktree merge prerequisites")
    merge_preflight_parser.add_argument("run_id")
    merge_preflight_parser.add_argument("--agent-id", default="worker-1")
    add_root(merge_preflight_parser)

    worktree_preview = subparsers.add_parser("worktree-preview", help="Generate worktree merge evidence bundle")
    worktree_preview.add_argument("run_id")
    worktree_preview.add_argument("--agent-id", default="worker-1")
    add_root(worktree_preview)

    review_accept_parser = subparsers.add_parser("review-accept", help="Record human review acceptance for a run")
    review_accept_parser.add_argument("run_id")
    review_accept_parser.add_argument("--agent-id", default="worker-1")
    add_root(review_accept_parser)

    worktree_apply = subparsers.add_parser("worktree-apply", help="Apply accepted worktree files to the main project")
    worktree_apply.add_argument("run_id")
    worktree_apply.add_argument("--agent-id", default="worker-1")
    add_root(worktree_apply)

    github_pr_body = subparsers.add_parser("github-pr-body", help="Generate a GitHub PR body from run evidence")
    github_pr_body.add_argument("run_id")
    add_root(github_pr_body)

    github_pr_create_parser = subparsers.add_parser("github-pr-create", help="Create a GitHub draft PR from run evidence")
    github_pr_create_parser.add_argument("run_id")
    github_pr_create_parser.add_argument("--draft", action="store_true")
    github_pr_create_parser.add_argument("--dry-run", action="store_true")
    add_root(github_pr_create_parser)

    github_pr_sync_parser = subparsers.add_parser("github-pr-sync", help="Update an existing GitHub PR body from run evidence")
    github_pr_sync_parser.add_argument("run_id")
    github_pr_sync_parser.add_argument("--dry-run", action="store_true")
    add_root(github_pr_sync_parser)

    github_ci_watch_parser = subparsers.add_parser("github-ci-watch", help="Wait for GitHub Actions checks on the current commit")
    github_ci_watch_parser.add_argument("--timeout", type=float, default=600.0)
    github_ci_watch_parser.add_argument("--poll", type=float, default=10.0)
    add_root(github_ci_watch_parser)

    github_pr_check_parser = subparsers.add_parser("github-pr-check", help="Verify GitHub PR files and checks against local run evidence")
    github_pr_check_parser.add_argument("run_id")
    add_root(github_pr_check_parser)

    github_issue_import = subparsers.add_parser("github-issue-import", help="Import a GitHub issue into a local task")
    github_issue_import.add_argument("issue_number")
    github_issue_import.add_argument("--from-file", default=None)
    add_root(github_issue_import)

    github_issue_comment = subparsers.add_parser("github-issue-comment", help="Write or preview a GitHub issue evidence comment")
    github_issue_comment.add_argument("run_id")
    github_issue_comment.add_argument("--issue", required=True)
    github_issue_comment.add_argument("--dry-run", action="store_true")
    add_root(github_issue_comment)

    github_pr_comments = subparsers.add_parser("github-pr-comments", help="Import GitHub PR comments into run evidence")
    github_pr_comments.add_argument("run_id")
    github_pr_comments.add_argument("--from-file", default=None)
    github_pr_comments.add_argument("--dry-run", action="store_true")
    add_root(github_pr_comments)

    privacy = subparsers.add_parser("privacy-scan", help="Scan tracked files for private paths, tokens, and local artifacts")
    add_root(privacy)

    release = subparsers.add_parser("release-check", help="Run release readiness checks")
    add_root(release)

    final_report = subparsers.add_parser("report", help="Generate a final run report")
    final_report.add_argument("run_id")
    add_root(final_report)

    orchestrate_parser = subparsers.add_parser("orchestrate", help="Start multiple pending tasks up to a safe review boundary")
    orchestrate_parser.add_argument("--parallel", type=int, default=2)
    orchestrate_parser.add_argument("--worktree", action="store_true")
    orchestrate_parser.add_argument("--run-codex", action="store_true")
    orchestrate_parser.add_argument("--watch", action="store_true")
    orchestrate_parser.add_argument("--timeout", type=float, default=1800.0)
    orchestrate_parser.add_argument("--run-command", default=None, help="Testing/advanced worker command template to run instead of codex")
    add_root(orchestrate_parser)

    auto_next_parser = subparsers.add_parser("auto-next", help="Run doctor, start next task, dispatch, optionally run Codex and watch")
    auto_next_parser.add_argument("--agent-id", default="worker-1")
    auto_next_parser.add_argument("--codex-command", action="store_true")
    auto_next_parser.add_argument("--run-codex", action="store_true")
    auto_next_parser.add_argument("--dry-run", action="store_true")
    auto_next_parser.add_argument("--watch", action="store_true")
    auto_next_parser.add_argument("--watch-timeout", type=float, default=300.0)
    auto_next_parser.add_argument("--worktree", action="store_true")
    auto_next_parser.add_argument("--worktree-path", default=None)
    add_root(auto_next_parser)

    accept = subparsers.add_parser("accept", help="Accept a run and move its task to done")
    accept.add_argument("run_id")
    accept.add_argument("--commit", action="store_true")
    add_root(accept)

    return parser


def add_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=None, help="Target project root")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        paths = resolve_paths(args.root)
        if args.command == "init":
            paths.ensure()
            print(f"initialized {paths.root}")
            return 0
        if args.command == "new-task":
            git_utils.require_git_repository(paths.root)
            config = load_config(paths.root)
            validation = args.validation or list(config.get("validation", {}).get("default_commands", []))
            task_path = create_task(paths, args.title, args.allowed, args.forbidden, validation)
            print(f"created {task_path.name}")
            return 0
        if args.command == "run-next":
            git_utils.require_git_repository(paths.root)
            paths.ensure()
            pending = first_pending(paths)
            if not pending:
                print("no pending tasks", file=sys.stderr)
                return 1
            active_path = activate_task(paths, pending)
            run_dir = create_run(paths, parse_task(active_path))
            print(f"started {run_dir.name}")
            return 0
        if args.command == "capture-diff":
            run_dir = get_run(paths, args.run_id)
            changed = git_utils.diff_name_only(paths.root)
            (run_dir / "changed-files.txt").write_text("\n".join(changed) + ("\n" if changed else ""), encoding="utf-8")
            (run_dir / "diff-stat.txt").write_text(git_utils.diff_stat(paths.root), encoding="utf-8")
            (run_dir / "diff.patch").write_text(git_utils.full_diff(paths.root), encoding="utf-8")
            print(f"captured {len(changed)} changed files")
            return 0
        if args.command == "scope-check":
            run_dir = get_run(paths, args.run_id)
            task = parse_task(run_dir / "input-task.md")
            changed_path = run_dir / "changed-files.txt"
            changed = changed_path.read_text(encoding="utf-8").splitlines() if changed_path.exists() else git_utils.diff_name_only(paths.root)
            result = check_scope(task, changed)
            write_scope_report(run_dir / "scope-check.yaml", result)
            print(result.status)
            return 0 if result.status == "ok" else 2
        if args.command == "review":
            run_dir = get_run(paths, args.run_id)
            review_path = create_review(run_dir)
            print(f"created {review_path}")
            return 0
        if args.command == "review-result":
            run_dir = get_run(paths, args.run_id)
            output = write_review_result(run_dir, args.decision, args.reason)
            print(f"created {output}")
            return 0
        if args.command == "revise":
            run_dir = get_run(paths, args.run_id)
            output = create_revise_prompt(run_dir, args.agent_id)
            print(f"created {output}")
            return 0
        if args.command == "dispatch":
            run_dir = get_run(paths, args.run_id)
            prompt_path = create_worker_prompt(run_dir, args.agent_id)
            print(f"created {prompt_path}")
            if args.codex_command:
                command_path = create_codex_command(run_dir, paths.root, args.agent_id)
                print(f"created {command_path}")
            return 0
        if args.command == "blocked":
            run_dir = get_run(paths, args.run_id)
            blocked_path = write_blocked(run_dir, args.agent_id, args.reason)
            print(f"blocked {blocked_path}")
            return 0
        if args.command == "complete":
            run_dir = get_run(paths, args.run_id)
            done_path = write_completion(run_dir, args.agent_id, args.result, args.message)
            print(f"completed {done_path}")
            return 0
        if args.command == "advance":
            run_dir = get_run(paths, args.run_id)
            try:
                advance_run(paths.root, run_dir, args.agent_id)
            except MissingDoneSignal as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 3
            except ScopeViolation as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(f"review_ready {args.run_id}")
            return 0
        if args.command == "watch":
            run_dir = get_run(paths, args.run_id)
            try:
                result = watch_run(paths.root, run_dir, args.agent_id, args.timeout, args.poll)
            except WorkerBlocked as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 4
            except WatchTimeout as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 3
            except ScopeViolation as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(f"{result} {args.run_id}")
            return 0
        if args.command == "run-codex":
            run_dir = get_run(paths, args.run_id)
            returncode, message = run_codex_worker(paths.root, run_dir, args.agent_id, args.dry_run, args.timeout)
            print(message)
            return returncode
        if args.command == "worktree-start":
            run_dir = get_run(paths, args.run_id)
            worktree_path, branch = start_worktree(paths.root, run_dir, args.agent_id, Path(args.path).resolve() if args.path else None)
            print(f"worktree {worktree_path}")
            print(f"branch {branch}")
            return 0
        if args.command == "worktree-collect":
            run_dir = get_run(paths, args.run_id)
            collect_worktree(paths.root, run_dir, args.agent_id)
            print(f"collected {args.run_id}")
            return 0
        if args.command == "merge-preflight":
            run_dir = get_run(paths, args.run_id)
            ok = merge_preflight(paths.root, run_dir, args.agent_id)
            print("ok" if ok else "fail")
            return 0 if ok else 1
        if args.command == "worktree-preview":
            run_dir = get_run(paths, args.run_id)
            ok = preview_worktree(paths.root, run_dir, args.agent_id)
            print("preview_ready" if ok else "scope_violation")
            return 0 if ok else 2
        if args.command == "review-accept":
            run_dir = get_run(paths, args.run_id)
            review_accept(run_dir, args.agent_id)
            print(f"review_accepted {args.run_id}")
            return 0
        if args.command == "worktree-apply":
            run_dir = get_run(paths, args.run_id)
            apply_worktree(paths.root, run_dir, args.agent_id)
            print(f"merge_ready {args.run_id}")
            return 0
        if args.command == "github-pr-body":
            run_dir = get_run(paths, args.run_id)
            output = pr_body(paths.root, run_dir)
            print(f"created {output}")
            return 0
        if args.command == "github-pr-create":
            run_dir = get_run(paths, args.run_id)
            returncode, output = github_pr_create(paths.root, run_dir, args.draft, args.dry_run)
            print(output)
            return returncode
        if args.command == "github-pr-sync":
            run_dir = get_run(paths, args.run_id)
            returncode, output = github_pr_sync(paths.root, run_dir, args.dry_run)
            print(output)
            return returncode
        if args.command == "github-ci-watch":
            returncode, output = github_ci_watch(paths.root, args.timeout, args.poll)
            print(output, end="")
            return returncode
        if args.command == "github-pr-check":
            run_dir = get_run(paths, args.run_id)
            returncode, output = github_pr_check(paths.root, run_dir)
            print(output, end="")
            return returncode
        if args.command == "github-issue-import":
            task_path = import_issue(paths, args.issue_number, Path(args.from_file) if args.from_file else None)
            print(f"created {task_path.name}")
            return 0
        if args.command == "github-issue-comment":
            write_issue_comment(paths, args.run_id, args.issue)
            command = issue_comment_command(args.issue, args.run_id)
            print(command)
            if args.dry_run:
                return 0
            result = subprocess.run(command.split(), cwd=paths.root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(result.stdout if result.returncode == 0 else result.stderr)
            return result.returncode
        if args.command == "github-pr-comments":
            run_dir = get_run(paths, args.run_id)
            output = write_pr_comments(run_dir, Path(args.from_file) if args.from_file else None)
            print(f"created {output}")
            return 0
        if args.command == "privacy-scan":
            returncode, output = privacy_scan(paths.root)
            print(f"created {output}")
            return returncode
        if args.command == "release-check":
            privacy_code, privacy_output = privacy_scan(paths.root)
            output = paths.root / ".agent-loop" / "release-check.yaml"
            output.parent.mkdir(parents=True, exist_ok=True)
            status_value = "ok" if privacy_code == 0 else "fail"
            output.write_text(f"status: {status_value}\nprivacy_scan: {privacy_output.name}\n", encoding="utf-8")
            print(f"created {output}")
            return privacy_code
        if args.command == "report":
            run_dir = get_run(paths, args.run_id)
            output = create_final_report(run_dir)
            print(f"created {output}")
            return 0
        if args.command == "orchestrate":
            for message in orchestrate(paths, args.parallel, args.worktree, args.run_codex, args.watch, args.timeout, args.run_command):
                print(message)
            return 0
        if args.command == "auto-next":
            try:
                returncode, messages = auto_next(
                    paths,
                    args.agent_id,
                    args.codex_command,
                    args.run_codex,
                    args.dry_run,
                    args.watch,
                    args.watch_timeout,
                    args.worktree,
                    Path(args.worktree_path).resolve() if args.worktree_path else None,
                )
            except AutoNextError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return exc.exit_code
            for message in messages:
                print(message)
            return returncode
        if args.command == "state":
            run_dir = get_run(paths, args.run_id)
            state_data = run_state(paths.root, run_dir)
            print(render_simple_yaml(state_data), end="")
            return 0
        if args.command == "resume":
            run_dir = get_run(paths, args.run_id)
            state_data = resume_run(paths.root, run_dir)
            print(render_simple_yaml(state_data), end="")
            return 0
        if args.command == "status":
            paths.ensure()
            pending_count = len(list(paths.pending_dir.glob("*.md")))
            active_count = len(list(paths.active_dir.glob("*.md")))
            done_count = len(list(paths.done_dir.glob("*.md")))
            run_count = len([item for item in paths.runs_dir.iterdir() if item.is_dir()])
            print(f"pending: {pending_count}")
            print(f"active: {active_count}")
            print(f"done: {done_count}")
            print(f"runs: {run_count}")
            return 0
        if args.command == "doctor":
            findings = run_doctor(paths)
            print(render_report(paths.root, findings), end="")
            return 1 if has_failures(findings) else 0
        if args.command == "github-doctor":
            findings = github_doctor(paths.root)
            print(render_github_doctor(paths.root, findings), end="")
            return 1 if github_has_failures(findings) else 0
        if args.command == "accept":
            if args.commit:
                git_utils.require_git_repository(paths.root)
            run_dir = get_run(paths, args.run_id)
            if args.commit and is_worktree_run(run_dir) and not is_merge_ready(run_dir):
                print("error: worktree run is not merge_ready; run worktree-collect, merge-preflight, worktree-preview, review-accept, and worktree-apply first", file=sys.stderr)
                return 1
            blocking_decision = decision_blocks_accept(run_dir)
            if blocking_decision:
                print(f"error: review decision is {blocking_decision}; run revise or change review-result before accept", file=sys.stderr)
                return 1
            task_id = run_task_id(run_dir)
            complete_active_task(paths, task_id)
            (run_dir / "status.yaml").write_text(
                (run_dir / "status.yaml").read_text(encoding="utf-8").replace("status: running", "status: accepted"),
                encoding="utf-8",
            )
            if args.commit:
                commit_result = commit_run(paths.root, args.run_id, task_id)
                if commit_result.returncode != 0:
                    print(commit_result.stderr, file=sys.stderr)
                    return commit_result.returncode
            print(f"accepted {args.run_id}")
            return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except MergeGateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command {args.command}")
    return 2


def render_simple_yaml(data: dict) -> str:
    lines = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            if value:
                lines.extend(f"  - {item}" for item in value)
            else:
                lines.append("  []")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"

def commit_run(root: Path, run_id: str, task_id: str) -> subprocess.CompletedProcess[str]:
    add = git_utils.git(root, "add", ".")
    if add.returncode != 0:
        return add
    return git_utils.git(root, "commit", "-m", f"{task_id}: accept {run_id}")


if __name__ == "__main__":
    raise SystemExit(main())
