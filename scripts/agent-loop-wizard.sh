#!/usr/bin/env bash
set -euo pipefail

if command -v agent-loop >/dev/null 2>&1; then
  AGENT_LOOP=(agent-loop)
else
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
  AGENT_LOOP=(python3 -m agent_loop.cli)
  export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
fi

ask_required() {
  local prompt="$1"
  local value=""
  while [[ -z "$value" ]]; do
    printf '%s: ' "$prompt" >&2
    IFS= read -r value
    if [[ -z "$value" ]]; then
      echo "This field is required." >&2
    fi
  done
  printf '%s' "$value"
}

ask_optional() {
  local prompt="$1"
  local default="${2:-}"
  local value=""
  if [[ -n "$default" ]]; then
    printf '%s [%s]: ' "$prompt" "$default" >&2
  else
    printf '%s: ' "$prompt" >&2
  fi
  IFS= read -r value
  if [[ -z "$value" ]]; then
    value="$default"
  fi
  printf '%s' "$value"
}

ask_yes_no() {
  local prompt="$1"
  local default="${2:-n}"
  local value=""
  printf '%s [%s]: ' "$prompt" "$default" >&2
  IFS= read -r value
  value="${value:-$default}"
  case "$value" in
    y|Y|yes|YES) printf 'y' ;;
    *) printf 'n' ;;
  esac
}

echo "Codex Agent Superteam Wizard"
echo "This wizard initializes a Git project, records a scoped task, and starts automation at a safe boundary.（本向导会初始化 Git 项目、记录有边界的任务，并在安全边界内启动自动化。）"
echo

ROOT="$(ask_required 'Project root path（项目根目录路径）')"
PROJECT_SUMMARY="$(ask_required 'Project name or short background（项目名称或简短背景）')"
TASK="$(ask_required 'Task / requirement to implement（要实现的任务或需求）')"
ALLOWED="$(ask_required 'Allowed path scope, e.g. docs/** or src/auth/**（允许修改的路径范围，例如 docs/** 或 src/auth/**）')"
FORBIDDEN="$(ask_optional 'Forbidden path scope (optional)（禁止修改的路径范围，可选）')"
VALIDATION="$(ask_optional 'Validation command (optional)（验证命令，可选）')"
PARALLEL="$(ask_optional 'Parallel workers（并行 worker 数量）' '1')"
USE_WORKTREE="$(ask_yes_no 'Use isolated Git worktree?（是否使用隔离的 Git worktree？）' 'n')"
RUN_CODEX="$(ask_yes_no 'Run Codex automatically now?（是否现在自动运行 Codex？）' 'n')"
REVIEW_POLICY="$(ask_optional 'Review policy: strict | smart | auto（审核策略：strict 严格人工 / smart 智能 / auto 自动）' 'strict')"

case "$REVIEW_POLICY" in
  strict|smart|auto) ;;
  *) echo "Invalid review policy: $REVIEW_POLICY" >&2; exit 2 ;;
esac

if [[ ! -d "$ROOT" ]]; then
  echo "Project root does not exist: $ROOT" >&2
  exit 2
fi
if ! git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Project root must be a Git repository: $ROOT" >&2
  exit 2
fi

echo
echo "Summary（摘要）"
echo "- Project: $PROJECT_SUMMARY"
echo "- Root: $ROOT"
echo "- Task: $TASK"
echo "- Allowed: $ALLOWED"
echo "- Forbidden: ${FORBIDDEN:-<none>}"
echo "- Validation: ${VALIDATION:-<none>}"
echo "- Parallel: $PARALLEL"
echo "- Worktree: $USE_WORKTREE"
echo "- Run Codex: $RUN_CODEX"
echo "- Review policy: $REVIEW_POLICY"
echo
CONFIRM="$(ask_yes_no 'Start this automation flow?（是否开始这次自动化流程？）' 'y')"
if [[ "$CONFIRM" != "y" ]]; then
  "${AGENT_LOOP[@]}" init --root "$ROOT"
  "${AGENT_LOOP[@]}" template-init --root "$ROOT"
  echo "Cancelled before orchestration. Initialization files are ready."
  exit 0
fi

"${AGENT_LOOP[@]}" self-test >/dev/null
"${AGENT_LOOP[@]}" init --root "$ROOT"
"${AGENT_LOOP[@]}" template-init --root "$ROOT"
"${AGENT_LOOP[@]}" doctor --root "$ROOT"

new_task=("${AGENT_LOOP[@]}" new-task "$TASK" --root "$ROOT" --allowed "$ALLOWED")
if [[ -n "$FORBIDDEN" ]]; then
  new_task+=(--forbidden "$FORBIDDEN")
fi
if [[ -n "$VALIDATION" ]]; then
  new_task+=(--validation "$VALIDATION")
fi
"${new_task[@]}"

orchestrate=("${AGENT_LOOP[@]}" orchestrate --root "$ROOT" --parallel "$PARALLEL")
if [[ "$USE_WORKTREE" == "y" ]]; then
  orchestrate+=(--worktree)
fi
if [[ "$RUN_CODEX" == "y" ]]; then
  orchestrate+=(--run-codex --watch)
fi
"${orchestrate[@]}"

cat > "$ROOT/.agent-loop/review-policy.yaml" <<EOF
review_policy: $REVIEW_POLICY
meaning: strict requires human acceptance; smart/auto may be used by future automation only when evidence is unambiguous and low risk.
EOF

"${AGENT_LOOP[@]}" status --root "$ROOT"
echo "Wizard complete. Review policy: $REVIEW_POLICY"
echo "Human gate: inspect evidence unless your policy automation later proves the run is unambiguous and low risk."
