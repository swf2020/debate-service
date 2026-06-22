## ADDED Requirements

### Requirement: 辩论列表页预加载演讲

系统 SHALL 在辩论历史列表页加载时，预加载所有已完成辩论的 speeches 摘要。

#### Scenario: 正常加载
- **WHEN** 用户登录并进入辩论历史列表页
- **THEN** 前端在获取辩论列表后，立即批量请求 `GET /api/debate/speeches/batch?ids=...` 获取所有已完成辩论的 speeches 摘要

#### Scenario: 无已完成辩论
- **WHEN** 用户没有已完成辩论
- **THEN** 前端跳过预加载请求

#### Scenario: 预加载失败
- **WHEN** 批量 speeches 请求失败
- **THEN** 前端记录错误但不影响辩论列表的正常展示，点击回放时回退到单独请求

### Requirement: 前端内存缓存

系统 SHALL 在前端维护辩论 speeches 的内存缓存。

#### Scenario: 缓存命中
- **WHEN** 用户点击"查看回放"且该 debate_id 的 speeches 已在前端内存缓存中
- **THEN** 前端直接使用缓存数据调用 `restoreSpeeches()`，不发起网络请求，即时渲染

#### Scenario: 缓存未命中
- **WHEN** 用户点击"查看回放"且该 debate_id 的 speeches 不在前端内存缓存中
- **THEN** 前端回退到 `GET /api/debate/{id}` 请求，并将结果存入缓存

#### Scenario: 缓存失效
- **WHEN** 用户删除一个辩论
- **THEN** 前端从内存缓存中移除该 debate_id 对应条目

### Requirement: 回放加载状态反馈

系统 SHALL 在回放加载过程中向用户提供视觉反馈。

#### Scenario: 从缓存加载
- **WHEN** speeches 从内存缓存加载（即时）
- **THEN** 辩论网格立即渲染，无加载指示器

#### Scenario: 从网络加载
- **WHEN** speeches 需要从 API 获取
- **THEN** 辩论网格显示加载状态（骨架屏或 spinner），API 返回后渲染内容

### Requirement: 演讲摘要格式

系统 SHALL 使用不含 thinking 内容的精简格式作为预加载的 speeches 摘要。

#### Scenario: 摘要字段
- **WHEN** 系统生成 speeches 摘要
- **THEN** 每条 speech 包含 `id`, `debater`, `phase`, `round_num`, `content`, `seq`, `speech_type`, `role_id`，不含 `thinking` 和 `created_at`
