# Codex Agent Loop Runtime Protocol

## 1. 单轮运行流程

```text
1. select task
2. create run directory
3. snapshot git HEAD/status
4. build context pack
5. assign worker or run locally
6. wait for done/blocked signal
7. collect git diff
8. scope guard check
9. run validation
10. review
11. revise if needed
12. commit or rollback
13. update task state
```

## 2. Run 目录

```text
.agent-runs/<run-id>/
  input-task.md
  before-head.txt
  before-status.txt
  context-pack.md
  status.yaml
  changed-files.txt
  diff.patch
  test-output.txt
  summary.md
  review.md
  mailbox/
```

## 3. 主 Agent 循环伪代码

```text
while has_pending_tasks:
  task = pick_next_task()
  run = create_run(task)
  snapshot_git(run)
  context = build_context_pack(task)
  worker = dispatch(context)

  while not terminal(worker):
    read_status_files()
    if blocked: decide_help_or_split()
    if timeout: mark_needs_attention()
    do_non_overlapping_work()

  collect_diff(run)
  if scope_violation: block_and_request_revision()
  run_validation()
  review = run_review()

  if review.accept:
    commit_checkpoint()
    close_task()
  elif review.revise and attempts < 3:
    dispatch_revision()
  elif review.split:
    create_smaller_tasks()
  else:
    rollback_or_escalate()
```

## 4. 不打断子 Agent 的规则

- 子 agent 正在 `running` 时，主 agent 不发新的实现要求。
- 主 agent 只读 `status.yaml`、`mailbox/` 和进程状态。
- 只有这些状态允许打断：`needs_info`、`blocked`、`timeout`、`scope_risk`。
- 如果需要修改子 agent 任务，创建 `revision-brief.md`，不要口头追加混乱要求。

## 5. 完成定义

子 agent 只有同时满足以下条件才算完成：

- 写入 `mailbox/<agent-id>.done.md`
- 更新 `status.yaml` 为 `done`
- 写入 `summary.md`
- 列出实际修改文件
- 给出验证结果或说明为何未验证

主 agent 必须再用 Git 检查实际修改，不能只相信子 agent summary。
