#!/usr/bin/env bash
set -euo pipefail

ROOT=""
TASK=""
ALLOWED=""
FORBIDDEN=""
VALIDATION=""
PARALLEL="2"
INIT_ONLY="0"
RUN_CODEX="0"
WORKTREE="0"
WATCH="0"

usage() {
  cat <<'EOF'
Usage:
  scripts/agent-loop-quickstart.sh --root /path/to/project [options]

Options:
  --init-only              Initialize config/templates and run doctor only.
  --task "Title"           Create a scoped task and start orchestration.
  --allowed 'path/**'      Allowed path scope for --task. Defaults to docs/**.
  --forbidden 'path/**'    Optional forbidden path scope.
  --validation 'command'   Optional validation command.
  --parallel N             Number of workers for orchestration. Default: 2.
  --worktree               Use isolated Git worktrees.
  --run-codex              Launch Codex workers. Omitted by default for safety.
  --watch                  Wait for worker mailbox signals.
  -h, --help               Show this help.

Safety:
  This script never runs accept, review-accept, worktree-apply, commit, or PR merge.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="${2:-}"; shift 2 ;;
    --task) TASK="${2:-}"; shift 2 ;;
    --allowed) ALLOWED="${2:-}"; shift 2 ;;
    --forbidden) FORBIDDEN="${2:-}"; shift 2 ;;
    --validation) VALIDATION="${2:-}"; shift 2 ;;
    --parallel) PARALLEL="${2:-}"; shift 2 ;;
    --init-only) INIT_ONLY="1"; shift ;;
    --worktree) WORKTREE="1"; shift ;;
    --run-codex) RUN_CODEX="1"; shift ;;
    --watch) WATCH="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$ROOT" ]]; then
  echo "error: --root is required" >&2
  usage >&2
  exit 2
fi

if [[ ! -d "$ROOT" ]]; then
  echo "error: root does not exist: $ROOT" >&2
  exit 2
fi

if command -v agent-loop >/dev/null 2>&1; then
  AGENT_LOOP=(agent-loop)
else
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
  AGENT_LOOP=(python3 -m agent_loop.cli)
  export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
fi

if ! git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "error: root must be a Git repository: $ROOT" >&2
  exit 2
fi

"${AGENT_LOOP[@]}" self-test >/dev/null
"${AGENT_LOOP[@]}" init --root "$ROOT"
if [[ "$INIT_ONLY" == "1" || -z "$TASK" ]]; then
  "${AGENT_LOOP[@]}" template-init --root "$ROOT" --github-templates
else
  "${AGENT_LOOP[@]}" template-init --root "$ROOT"
fi
"${AGENT_LOOP[@]}" doctor --root "$ROOT"

if [[ "$INIT_ONLY" == "1" ]]; then
  echo "Quickstart complete: initialized $ROOT"
  exit 0
fi

if [[ -z "$TASK" ]]; then
  echo "Quickstart complete: initialized $ROOT"
  echo "Next: rerun with --task \"Your task\" --allowed 'path/**' to start a bounded run."
  exit 0
fi

if [[ -z "$ALLOWED" ]]; then
  ALLOWED="docs/**"
fi

new_task=("${AGENT_LOOP[@]}" new-task "$TASK" --root "$ROOT" --allowed "$ALLOWED")
if [[ -n "$FORBIDDEN" ]]; then
  new_task+=(--forbidden "$FORBIDDEN")
fi
if [[ -n "$VALIDATION" ]]; then
  new_task+=(--validation "$VALIDATION")
fi
"${new_task[@]}"

orchestrate=("${AGENT_LOOP[@]}" orchestrate --root "$ROOT" --parallel "$PARALLEL")
if [[ "$WORKTREE" == "1" ]]; then
  orchestrate+=(--worktree)
fi
if [[ "$RUN_CODEX" == "1" ]]; then
  orchestrate+=(--run-codex)
fi
if [[ "$WATCH" == "1" ]]; then
  orchestrate+=(--watch)
fi
"${orchestrate[@]}"

"${AGENT_LOOP[@]}" status --root "$ROOT"
echo "Quickstart complete: task queued/started for $ROOT"
echo "Human gate: inspect evidence before accept/apply/merge. Try: agent-loop status --root \"$ROOT\""
