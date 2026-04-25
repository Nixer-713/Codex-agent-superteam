# Codex Agent Loop

一个基于 Codex、Git、任务队列、审阅门禁和项目记忆层的自动化任务循环框架草案。

目标不是简单复制 Claude Agent Team，而是把它的有效机制映射到 Codex/终端/GitHub 工作流：

- shared task list → `tasks/`、GitHub Issues、PR checklist
- mailbox / notification → `agent-runs/*/mailbox/`、summary 文件、主 agent 轮询
- file locking → `locks/`、branch/worktree ownership、scope guard
- token 节约 → manifest、摘要、分层上下文包、按需读取 diff
- review loop → self-review、peer-review、CI、human gate
- idle / done signal → `DONE.md`、`status.yaml`、exit code、PR comment

核心文档：

- `docs/system-architecture.md`：完整系统构造
- `docs/runtime-protocol.md`：每轮任务运行协议
- `docs/reference-insights.md`：Karpathy/Superpowers/Oh My Codex 借鉴点
- `protocols/execution-protocol.md`：Codex worker/reviewer 底层执行协议
- `protocols/karpathy-coding-guidelines.md`：karpathy提示词执行准则
- `templates/`：任务、子代理、审阅与运行记录模板

当前状态：这是第一版架构设计，不包含可执行 runner。下一步可以基于这些模板实现本地 CLI 或 GitHub Actions 版。

## Local CLI MVP

Run commands from this directory with `python3 -m agent_loop.cli`, or install the package later to use `agent-loop`.

### Basic Flow

```bash
PROJECT_ROOT="/Users/nixer/codex储备/测试"

python3 -m agent_loop.cli init --root "$PROJECT_ROOT"
python3 -m agent_loop.cli doctor --root "$PROJECT_ROOT"
python3 -m agent_loop.cli new-task "Add login validation" --root "$PROJECT_ROOT" --allowed 'src/auth/**' --forbidden 'infra/**' --validation 'python3 -m pytest'
python3 -m agent_loop.cli run-next --root "$PROJECT_ROOT"
python3 -m agent_loop.cli dispatch <run-id> --root "$PROJECT_ROOT" --agent-id worker-auth --codex-command
python3 -m agent_loop.cli complete <run-id> --root "$PROJECT_ROOT" --agent-id worker-auth --result success --message "Worker finished the assigned task."
python3 -m agent_loop.cli watch <run-id> --root "$PROJECT_ROOT" --agent-id worker-auth --timeout 300
python3 -m agent_loop.cli accept <run-id> --root "$PROJECT_ROOT"
```

`/path/to/project` 这类字符串只是文档占位符，不要原样执行；请替换成真实项目目录。

### Automation Boundary

The MVP automates task/run artifact creation, bounded worker prompt generation, worker completion signals, Git diff capture, scope checks, review file generation, and task state transitions. `advance` moves a completed worker run to `review_ready`; human approval is still required at the final `accept` boundary, which keeps uncertain or high-risk decisions outside automatic execution.

`dispatch --codex-command` writes a runnable `codex exec` shell command beside the worker prompt. It is intentionally generated but not executed by default, so you can inspect the command before allowing a worker to modify code.

`run-codex --dry-run` prints the exact `codex exec` command without executing it. Without `--dry-run`, it runs `codex exec` with `workspace-write` sandboxing and writes logs into the run directory. It still does not auto-accept or commit; use `watch`, review, then `accept`.

`watch` waits for `mailbox/<agent-id>.done.md` or `mailbox/<agent-id>.blocked.md`. A done signal automatically runs the review-prep pipeline; a blocked signal stops and returns control to the human operator.

For parallel local work, create one Git worktree per worker:

```bash
python3 -m agent_loop.cli worktree-start <run-id> --root "$PROJECT_ROOT" --agent-id worker-auth --path ../project-worker-auth
```

This creates a `codex/<task-id>-<agent-id>` branch and records the assignment in the run's `worktrees.yaml`.

Worktree runs require an evidence chain before merging back:

```bash
python3 -m agent_loop.cli worktree-collect <run-id> --root "$PROJECT_ROOT" --agent-id worker-docs
python3 -m agent_loop.cli merge-preflight <run-id> --root "$PROJECT_ROOT" --agent-id worker-docs
python3 -m agent_loop.cli worktree-preview <run-id> --root "$PROJECT_ROOT" --agent-id worker-docs
python3 -m agent_loop.cli review-accept <run-id> --root "$PROJECT_ROOT" --agent-id worker-docs
python3 -m agent_loop.cli worktree-apply <run-id> --root "$PROJECT_ROOT" --agent-id worker-docs
python3 -m agent_loop.cli accept <run-id> --root "$PROJECT_ROOT" --commit
```

`accept --commit` refuses worktree runs until `worktree-apply` produces `merge-result.yaml` with `match: true` and marks the run `merge_ready`.

### Auto Next

Use `auto-next` to run the safe automation chain up to the human review boundary:

```bash
python3 -m agent_loop.cli auto-next --root "$PROJECT_ROOT" --agent-id worker-1 --codex-command
```

Optional flags:

- `--run-codex`: execute `codex exec` for the generated worker prompt.
- `--dry-run`: preview the `codex exec` command without running it.
- `--watch`: wait for done/blocked and automatically prepare review artifacts.
- `--watch-timeout 300`: cap waiting time in seconds.

`auto-next` never runs `accept` or commits. It stops at `review_ready` so a human can inspect the diff and decide.

## GitHub CLI Workflow

Use GitHub as the remote audit and review layer after local evidence is ready:

```bash
python3 -m agent_loop.cli github-doctor --root "$PROJECT_ROOT"
python3 -m agent_loop.cli github-pr-body <run-id> --root "$PROJECT_ROOT"
python3 -m agent_loop.cli github-pr-create <run-id> --root "$PROJECT_ROOT" --draft
python3 -m agent_loop.cli github-pr-sync <run-id> --root "$PROJECT_ROOT"
```

`github-pr-body` writes `github-pr-body.md` into the run directory with task, changed files, scope, risk, validation, review, and diff preview sections. `github-pr-create` pushes the current feature branch and creates a draft PR; it refuses to run from `main`/`master` and does not merge. `github-pr-sync` regenerates the same evidence-based body and updates the current branch's existing PR with `gh pr edit --body-file`.

For safe previews, add `--dry-run` to `github-pr-create` or `github-pr-sync`; this prints the Git/GitHub commands without contacting GitHub.

GitHub then provides the remote debugging trail: PR Files changed, commit diffs, CI logs, review comments, blame, compare, and revert.

The repository includes GitHub Actions CI at `.github/workflows/test.yml`. It runs `python3 -m pytest -q` on pull requests and on pushes to `main` or `codex/**` branches, so every PR gets a remote test result in addition to local run evidence.

For isolated parallel workers, combine `auto-next` with `--worktree`:

```bash
python3 -m agent_loop.cli auto-next --root "$PROJECT_ROOT" --agent-id worker-docs --worktree --worktree-path ../project-worker-docs --codex-command
```

The run artifacts stay in the main project, while the generated `codex exec` command uses the worker worktree as its `--cd` directory.

### Doctor

Use `doctor` before automation or when the loop feels stuck:

```bash
python3 -m agent_loop.cli doctor --root "$PROJECT_ROOT"
```

It reports `[OK]`, `[WARN]`, and `[FAIL]` findings for Git setup, workspace directories, task counts, run artifacts, review-ready runs, and recorded scope violations. A `[FAIL]` exits non-zero and should block further automation until fixed.
