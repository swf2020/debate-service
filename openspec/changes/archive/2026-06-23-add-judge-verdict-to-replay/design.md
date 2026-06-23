## Context

辩论结束时，`debate_flow.py` 的 `judge_verdict()` 将判决写入 SQLite（`db.set_verdict`）并通过 SSE 实时推送 `SSEVerdictChunk` 和 `SSEDebateEnd`。但 Redis 缓存层（`redis_cache.py`）目前只缓存 speeches（`debate:{id}:speeches` / `debate:{id}:summary`），不缓存 verdict。

当用户重连 SSE 流（`GET /api/debate/{id}/stream`）时，`SSEHistoryReplay` 事件仅包含 speeches 列表，不包含 verdict。前端 `debate.js` 的 `history_replay` 分支尝试检查 `msg.verdict`，但该字段始终为 `undefined`。结果：已完成辩论的回放页面缺少裁判判决展示。

`GET /api/debate/{id}` REST 端点虽然返回 verdict（通过 `get_debate()` 读取 SQLite），但回放优先走 SSE 路径，不走 REST。

## Goals / Non-Goals

**Goals:**
- Redis 新增 `debate:{id}:verdict` 键，缓存完整判决 JSON
- `SSEHistoryReplay` 模型新增 `verdict` 和 `winner` 可选字段
- SSE 重连路径从 Redis/DB 读取 verdict 并填入 `SSEHistoryReplay`
- `GET /api/debate/{id}` 优先从 Redis 读取 verdict
- 删除辩论时同步清除 verdict 缓存键
- 前端 `history_replay` 渲染 verdict（无需额外 API 调用）

**Non-Goals:**
- 不修改 `judge_verdict()` 阶段的实时 SSE 推送逻辑（已在正常工作）
- 不修改 `debate_flow_standard.py`（标准格式已通过同一路径处理）
- 不新增 Redis 依赖（已引入）
- 不修改前端 `showVerdict()` 函数（已支持所需格式）

## Decisions

### 1. Redis 键设计

**选择**: `debate:{debate_id}:verdict` 存储 JSON 字符串，TTL 与 speeches 一致（24h）。

**理由**: 遵循现有键命名约定（`debate:{id}:speeches` / `debate:{id}:summary`）。单一键足够承载整个 verdict dict（< 5KB）。

**备选方案**: 将 verdict 嵌入 `debate:{id}:summary`。不选原因：summary 语义上是 speeches 列表的摘要，混入 verdict 违反单一职责。

### 2. SSEHistoryReplay 模型扩展

**选择**: 新增 `verdict: dict | None = None` 和 `winner: str | None = None` 可选字段。

**理由**: 向前兼容。旧客户端忽略未知字段，新客户端读取。不影响现有 `model_dump_json()` 行为。

**备选方案**: 单独追加一个 `verdict_replay` SSE 事件。不选原因：增加一条异步消息顺序依赖，前端需额外状态管理。

### 3. 重连路径数据流

**选择**: 在 main.py 构建 `SSEHistoryReplay` 时，先查 `cache.get_verdict(debate_id)`，miss 时从 `get_debate()` 读取并回填 Redis。

**理由**: 尽可能走 Redis 快速路径，仅在缓存过期时回退 SQLite。

### 4. REST 端点优先读缓存

**选择**: `GET /api/debate/{id}` 中优先从 `cache.get_verdict()` 读取，miss 时从已查询的 debate 对象中获取（该对象已包含 verdict）。

**理由**: 该端点已经查询了 `get_debate()`（返回 verdict），但如果缓存命中可避免反序列化 JSON。

## Risks / Trade-offs

- **[轻微] 数据一致性**: 缓存过期后回放可能短暂缺失 verdict → 回退 SQLite 查询保证最终一致
- **[轻微] 存储开销**: 每条 verdict 约 2-5KB → 1000 条辩论 = 最多 5MB，可忽略
- **[无] 向后兼容**: `SSEHistoryReplay` 新增可选字段，旧客户端忽略
