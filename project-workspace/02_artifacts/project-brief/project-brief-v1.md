---
artifact_type: project_brief
owner_skill: project-framer
status: draft
version: v1
created_at: 2026-04-25
---

# Project Brief: Codex Agent Loop

## A. Project Definition

Codex Agent Loop 是一个基于 Codex、Git、任务文件、运行记录、审阅门禁和项目记忆层的自动化任务循环框架，用于让 Codex APP/CLI 在大型项目中更稳定地执行“任务 → 审阅 → 修正 → 提交 → 下一轮”的持续开发流程。

## B. Input Analysis

### User-Provided Facts

- 目标目录是 `/Users/nixer/codex储备`。
- 需要创建一个文件夹存放基于 Codex 的自动化任务运行框架。
- 需要参考 Claude Agent Team 官方文档和 Datawhale 第三方教程。
- 必须考虑上下文长度爆炸、token 消耗过高、子代理完成标志、主 agent 不打断子 agent、快速定位问题、减小代码侵入性和 review 循环。

### Reasonable Inferences

- 该系统面向大型项目或长期项目，而不是一次性脚本。
- Git commit/diff 会作为事实记录和回滚检查点。
- 用户希望先完成系统构造设计，再进入实现。

### Open Questions

- 首个可执行版本应优先做本地 CLI，还是 GitHub Issue/PR 集成？
- 子 agent 是通过 Codex 多线程人工分派，还是后续实现脚本化 runner？
- 是否需要兼容 Claude Code、Gemini CLI 等其他 agent CLI？

## C. Scenario Expansion

- 个人大型项目：本地 task 文件 + git diff + review gate。
- 团队项目：GitHub Issues + branch/worktree + PR + CI。
- 多 agent 并发：每个 agent 独占 worktree 和路径 ownership，通过 mailbox 文件回传状态。

## D. Core Users And Value

- 独立开发者：获得稳定、可回滚的 Codex 长任务循环。
- 小团队负责人：用 PR/CI/review 管住 agent 代码改动。
- AI workflow 搭建者：构建 Git-backed agent team。

## E. Functional Modules

- Task queue
- Context pack generator
- Main orchestrator
- Subagent worker protocol
- Mailbox/status signal
- Diff monitor
- Scope guard
- Review loop
- Git checkpoint
- Project memory

## F. Capability Map

详见 `docs/system-architecture.md`。

## G. Project Background Narrative

当前 coding agent 已经能完成局部编码，但在大型项目里常见问题是上下文爆炸、任务边界不清、越界修改、难以审阅和缺少持续状态。Codex Agent Loop 用 Git 和文件系统作为共享事实层，把 agent 协作从纯聊天变成工程化流程。

## H. MVP Suggestion

第一版只做本地文件版：任务模板、运行目录、diff 采集、scope guard、review 模板和 commit checkpoint。暂不做完全自动化 GitHub bot。

## I. Risks And Open Questions

- 过度自动化可能提交错误代码。
- 多 agent 并发如果没有 worktree 隔离会冲突。
- review prompt 如果读取全量 diff，token 消耗会高。
- scope guard 不严会导致 agent 越界改代码。

## J. Next-Step Checklist

- [ ] 确认 MVP 形态：本地 CLI 或 GitHub PR。
- [ ] 实现 `agent-loop init`。
- [ ] 实现 `agent-loop run-next`。
- [ ] 实现 diff/scope guard。
- [ ] 实现 review prompt。
- [ ] 实现 run artifact 归档。
