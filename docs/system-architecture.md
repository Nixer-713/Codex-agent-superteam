# Codex Agent Loop 系统构造草案

## 0. 设计目标

Codex Agent Loop 是一个让 Codex APP / Codex CLI 更接近“agent team 持续协作”的工程化框架。它用 Git、任务文件、运行记录、审阅门禁和项目记忆层，把一次性对话变成可追踪、可恢复、可审阅、可持续推进的任务循环。

它的目标不是让多个 agent 无限制自动乱跑，而是建立一个可控循环：

```text
任务入队 → 主 agent 分派 → 子 agent 执行 → 完成信号 → diff 采集 → review → 修正 → commit/PR → 下一轮任务
```

## 1. 参考来源与映射

参考 Claude Agent Team 官方文档和第三方教程时，重点吸收的是“协作机制”，不是照搬具体实现。

| Claude Agent Team 机制 | Codex Agent Loop 映射 |
|---|---|
| shared task list | `tasks/`、GitHub Issues、`workflow-state.yaml` |
| subagent delegation | Codex 子线程、并行终端、git worktree、脚本 runner |
| mailbox / idle notification | `agent-runs/<run>/mailbox/`、`DONE.md`、`status.yaml` |
| file locking | `locks/`、branch/worktree ownership、路径级 scope guard |
| token 成本控制 | 分层上下文包、manifest、摘要、按需 diff、局部索引 |
| review loop | Codex self-review、reviewer agent、CI、human approval |
| background work | 主 agent 只监控状态文件，不反复打断子 agent |

## 2. 核心原则

### 2.1 Git 是事实层，不是全部状态层

Git 负责记录“实际发生了什么”：

- 修改了哪些文件
- 每个文件的 diff
- 每轮任务的 commit checkpoint
- 失败时的回滚点
- PR 中的审阅记录

但 Git 不负责表达全部意图。任务意图、验收标准、风险判断、review 结论应该写入任务文件和运行记录。

### 2.2 主 agent 是调度器，不是全知上下文容器

主 agent 不应该把所有源码、所有 diff、所有子 agent 输出都塞进上下文。主 agent 只维护：

- 当前任务队列
- 子 agent 状态摘要
- 修改文件 manifest
- 风险等级
- review 结论
- 下一步决策

详细上下文存到文件，需要时再按需读取。

### 2.3 子 agent 拥有清晰任务边界

每个子 agent 必须有：

- 单一任务目标
- 允许修改的路径范围
- 禁止修改的路径范围
- 完成标志
- 输出摘要
- 验证命令
- 回传给主 agent 的最小消息

### 2.4 每轮循环必须可暂停、可恢复、可回滚

任何时刻都应该能回答：

- 当前跑到哪一轮？
- 哪些子 agent 正在工作？
- 哪些文件被谁声明占用？
- 当前 diff 来自哪个任务？
- 是否已经 review？
- 是否可以 commit？
- 如果失败，回滚到哪个 commit？

## 3. 推荐目录结构

```text
codex-agent-loop/
  README.md
  docs/
    system-architecture.md
    runtime-protocol.md
  templates/
    task.template.md
    subagent-brief.template.md
    run-status.template.yaml
    review.template.md
  project-workspace/
    current-overview.md
    workflow-state.yaml
    artifact-index.yaml
    review-status.yaml
    02_artifacts/
    04_handoffs/
    05_reviews/
    06_logs/
```

在真实项目中，建议增加：

```text
.tasks/
  pending/
  active/
  blocked/
  done/
.agent-runs/
  run-YYYYMMDD-HHMMSS-task-id/
    input-task.md
    before-head.txt
    context-pack.md
    changed-files.txt
    diff.patch
    summary.md
    review.md
    status.yaml
    mailbox/
      worker-1.done.md
      reviewer-1.findings.md
.locks/
  paths.yaml
```

## 4. 主 Agent 职责

主 agent 是 orchestrator，职责是控制流程，而不是亲自做所有工作。

### 4.1 任务调度

- 从 `tasks/pending/` 或 GitHub Issues 中选择下一个任务
- 判断任务是否可执行
- 拆分成可并行的子任务
- 为每个子任务分配写权限范围
- 创建 run 目录和初始状态文件

### 4.2 上下文打包

主 agent 给子 agent 的上下文包必须短而精确：

- 任务目标
- 验收标准
- 相关文件路径
- 允许修改路径
- 禁止修改路径
- 必读文档摘要
- 最近相关 commit 摘要
- 本轮输出要求

禁止把整个项目塞给子 agent。

### 4.3 状态监控

主 agent 不应该每隔几秒去打断子 agent 问“做完了吗”。它只看外部状态：

- `status.yaml`
- `DONE.md`
- `mailbox/*.done.md`
- 子进程 exit code
- Git working tree 状态

### 4.4 Review 决策

主 agent 收到完成信号后：

1. 读取子 agent summary
2. 采集 `git diff --stat`
3. 判断是否越界修改
4. 运行必要测试
5. 发起 self-review / peer-review
6. 决定 accept、revise、split、rollback 或 escalate

## 5. 子 Agent 职责

子 agent 是 bounded worker，不应该自行扩大任务范围。

每个子 agent 必须遵守：

- 只做 brief 指定任务
- 只改 ownership 范围内文件
- 遇到范围外问题，写入 `blocked.md`，不要擅自修
- 完成后写 `summary.md` 和 `DONE.md`
- 不主动 commit，除非主 agent 明确授权
- 不删除或覆盖其他 agent 的文件

## 6. 子 Agent 完成标志如何回传主 Agent

建议采用多层完成信号，避免单一信号丢失。

### 6.1 文件信号

每个子 agent 完成后写：

```text
.agent-runs/<run-id>/mailbox/<agent-id>.done.md
```

内容包括：

```yaml
agent_id: worker-auth-ui
status: done
result: success
changed_files:
  - apps/web/src/auth/Login.tsx
validation:
  - command: pnpm test auth
    result: passed
needs_review: true
next_recommendation: run reviewer
```

### 6.2 状态机信号

同时更新：

```yaml
agents:
  worker-auth-ui:
    status: done
    last_update: 2026-04-25T22:00:00+08:00
    output: mailbox/worker-auth-ui.done.md
```

### 6.3 进程信号

如果是脚本 runner：

- exit code `0`：成功完成
- exit code `10`：任务阻塞，需要主 agent 决策
- exit code `20`：发现越界风险
- exit code `30`：验证失败
- exit code `40`：上下文不足

### 6.4 Git 信号

完成后主 agent 采集：

```bash
git status --short
git diff --stat
git diff --name-only
```

文件信号说明“agent 声称做了什么”，Git 信号说明“实际上改了什么”。两者必须对齐。

## 7. 主 Agent 如何保证不打断子 Agent 工作

### 7.1 不轮询对话，轮询文件

主 agent 不直接对运行中的子 agent 连续追问。它只读取：

- `status.yaml`
- `mailbox/`
- `locks/`
- 进程状态

### 7.2 任务分派后进入等待策略

主 agent 分派后只做非重叠工作：

- 准备 review checklist
- 读取相关文档
- 检查 CI 配置
- 规划下一批任务

除非子 agent 超时、写入 blocked、或显式请求帮助，否则不干预。

### 7.3 使用 worktree 隔离并行任务

大型项目中，并行子 agent 不应在同一个 working tree 里改代码。推荐：

```bash
git worktree add ../repo-task-123 -b codex/task-123
```

每个子 agent 独占一个 worktree，最后通过 PR 或 patch merge 回主线。

## 8. 上下文长度爆炸与 Token 控制

### 8.1 分层上下文

把上下文分成四层：

| 层级 | 内容 | 何时读取 |
|---|---|---|
| L0 | 任务 brief、验收标准、scope | 每个 agent 必读 |
| L1 | 相关文件 manifest、架构摘要 | 默认读取摘要 |
| L2 | 具体源码片段、diff | 按需读取 |
| L3 | 全量日志、大文件、历史 commit | 只有排障时读取 |

### 8.2 Context Pack

每轮任务生成一个短上下文包：

```text
context-pack.md
- task goal
- acceptance criteria
- allowed paths
- relevant files
- known constraints
- previous related decisions
- commands to verify
```

控制在 1,000-2,000 tokens 内。

### 8.3 Manifest 优先，不传全文

对子 agent 优先提供：

```text
file: apps/web/src/auth/Login.tsx
role: login UI component
why relevant: task modifies validation behavior
last touched: commit abc123
risk: medium
```

只有子 agent 确认需要时再读文件全文。

### 8.4 摘要滚动压缩

每轮结束后生成：

- `summary.md`：人类可读
- `machine-summary.yaml`：机器可读
- `changed-files.txt`：文件列表
- `diff.patch`：完整事实，默认不塞进上下文

下一轮只读取 summary 和 changed-files，必要时再读取 patch。

### 8.5 Token 预算规则

建议默认预算：

- task brief：≤ 800 tokens
- context pack：≤ 2,000 tokens
- subagent output：≤ 1,500 tokens
- review report：≤ 2,000 tokens
- 主 agent 汇总上下文：≤ 4,000 tokens

超过预算时必须写文件，不进入 prompt。

## 9. 快速定位问题所在

### 9.1 每轮必须保存最小诊断集

```text
before-head.txt
changed-files.txt
diff.patch
test-output.txt
summary.md
review.md
status.yaml
```

### 9.2 错误归类

review 或测试失败时，先归类：

- scope violation：改了不该改的文件
- compile failure：构建失败
- test failure：测试失败
- behavior mismatch：不满足验收标准
- regression risk：可能破坏旧功能
- architecture drift：偏离既有架构
- context gap：子 agent 缺少关键信息

### 9.3 二分定位

大型 diff 失败时，不让 agent 盲修。先做：

```bash
git diff --name-only
git diff --stat
```

按文件、模块、commit、测试用例缩小范围。必要时把任务拆成更小 patch。

### 9.4 失败复盘模板

每次失败写：

```text
What failed?
Where is the evidence?
Which file introduced it?
Is it scope, logic, test, or environment?
What is the smallest safe fix?
Should we rollback, revise, or split?
```

## 10. 尽量减小代码侵入性

### 10.1 默认不改业务结构

除非任务要求，否则禁止：

- 大规模重命名
- 跨模块重构
- 格式化整个仓库
- 修改公共 API
- 改构建系统
- 升级依赖
- 顺手修 unrelated bug

### 10.2 Patch 面积预算

按风险设置 patch 面积阈值：

| 风险 | 文件数 | 行数 |
|---|---:|---:|
| low | ≤ 3 | ≤ 150 |
| medium | ≤ 8 | ≤ 500 |
| high | > 8 | > 500 |

超过阈值时必须进入 review 或拆任务。

### 10.3 Scope Guard

每个任务声明：

```yaml
allowed_paths:
  - apps/web/src/auth/**
forbidden_paths:
  - packages/db/migrations/**
  - infra/**
```

主 agent 在 review 前比较 `git diff --name-only`。越界则 block。

### 10.4 Adapter 优先

如果必须扩展功能，优先：

- 增加小型 adapter
- 增加局部 helper
- 增加测试覆盖
- 保持原 API 不变

避免全局改造。

## 11. Review 循环

### 11.1 四层 Review

```text
Worker self-check
→ Codex reviewer diff review
→ Test/CI verification
→ Human or owner approval
```

### 11.2 Review 输入

reviewer 不读取整个项目，只读取：

- task brief
- acceptance criteria
- changed-files.txt
- diff.patch
- test-output.txt
- worker summary

### 11.3 Review 输出

review 必须给出明确结论：

```yaml
decision: accept | revise | split | rollback | escalate
blocking_findings:
  - file:
    issue:
    evidence:
    required_fix:
non_blocking_notes:
  - note:
next_action:
```

### 11.4 修正循环

如果 `revise`：

```text
review findings → worker revise brief → worker patch → diff delta → reviewer re-check
```

限制最多 3 轮。超过 3 轮必须拆任务或人工介入。

## 12. 多 Agent 并发策略

### 12.1 可并行的任务

可以并行：

- 不同模块
- 文档和代码
- 前端组件和后端 API mock
- 测试补充和实现补充，但要明确文件 ownership

不建议并行：

- 同一文件
- 同一公共 API
- 同一数据库 schema
- 同一构建配置

### 12.2 Ownership 声明

每个子 agent brief 必须包含：

```yaml
owned_paths:
  - apps/web/src/auth/Login.tsx
read_only_paths:
  - packages/api/src/auth.ts
blocked_paths:
  - packages/db/**
```

### 12.3 Lock 文件

```yaml
locks:
  apps/web/src/auth/Login.tsx:
    owner: worker-auth-ui
    expires_at: 2026-04-25T23:00:00+08:00
```

主 agent 分派前检查 lock，避免冲突。

## 13. GitHub 集成路线

### 13.1 本地模式

```text
task file → local branch → codex run → diff/review → commit
```

### 13.2 GitHub 模式

```text
Issue → branch → Codex run → push → PR → CI → review → merge
```

### 13.3 Commit Message 规范

```text
<task-id>: <short outcome>

- Goal: ...
- Changed: ...
- Validation: ...
- Review: accept/revise
```

### 13.4 PR 描述规范

PR 必须包含：

- linked issue
- task goal
- changed files summary
- verification result
- risk notes
- rollback plan

## 14. 状态机

任务状态：

```text
pending → planned → assigned → running → done_by_worker → reviewing → revising → accepted → committed → closed
                         ↘ blocked ↘ failed ↘ rollback_needed
```

主 agent 状态：

```text
idle → planning → dispatching → monitoring → reviewing → integrating → next_task
```

子 agent 状态：

```text
created → running → needs_info → done → failed → abandoned
```

## 15. 最小 MVP

第一阶段只做本地文件版：

1. `tasks/pending/*.md` 作为任务队列
2. 每轮创建 `.agent-runs/<run-id>/`
3. 任务前保存 `before-head.txt`
4. Codex 执行后保存 `changed-files.txt` 和 `diff.patch`
5. 生成 `summary.md`
6. 运行 review prompt
7. 通过后 commit
8. 移动任务到 `tasks/done/`

不做复杂 UI，不做自动 merge，不做完全无人值守。

## 16. 后续演进

### Phase 1：本地单 agent loop

- task template
- run directory
- diff capture
- review template

### Phase 2：本地多 agent loop

- worktree isolation
- locks
- mailbox
- subagent status

### Phase 3：GitHub PR loop

- GitHub Issues
- branch naming
- PR creation
- CI summary
- review comments

### Phase 4：长期项目记忆

- architecture index
- decision records
- module ownership
- failure knowledge base

### Phase 5：自动调度器

- task dependency graph
- risk classifier
- context pack generator
- reviewer routing

## 17. 关键结论

这个系统可行，但不要把重点放在“让 agent 无限自动运行”。真正重要的是：

```text
小任务边界 + Git 事实记录 + 外部状态文件 + 低 token 上下文 + review gate + 可回滚 checkpoint
```

Codex 版 agent team 最稳定的形态不是“聊天里多个智能体互相说话”，而是“文件系统和 Git 作为共享现实，主 agent 调度，子 agent 有边界执行，review gate 决定是否进入下一轮”。
