## Context

当前架构：辩论演讲存储在 SQLite `speeches` 表中，每次读取都执行 `SELECT * FROM speeches WHERE debate_id = ? ORDER BY seq`。前端仅在点击"查看回放"时通过 `GET /api/debate/{id}` 加载演讲内容，历史列表页（`GET /api/debates`）仅返回元数据。无任何缓存层，每个 `get_speeches()` 调用都打开新连接、查询、关闭。

目标：引入 Redis 作为演讲缓存，前端在历史列表页预加载演讲摘要，点击回放时即时渲染。

约束：
- 保持 SQLite 为 source of truth（Redis 仅作缓存）
- 不破坏现有 API 契约
- 不改变 SSE 实时流式传输逻辑
- 遵循现有代码风格（async/await、FastAPI、模块化 JS）

## Goals / Non-Goals

**Goals:**
- Redis 缓存层：辩论结束时自动写入，读取时优先命中缓存
- 前端预加载：历史列表页加载时，批量获取所有已完成辩论的 speeches 摘要
- 即时回放：点击"查看回放"优先使用前端内存缓存，零网络延迟
- 缓存失效：删除辩论时同步清除 Redis 缓存；24h TTL 自动过期

**Non-Goals:**
- 不改造 SSE 实时推送流程（保持现有 `history_replay` 事件逻辑）
- 不引入 Redis 做消息队列或 pub/sub（仅做缓存）
- 不改变 `debate_flow.py` / `debate_flow_standard.py` 的演讲持久化逻辑
- 不修改 `_persist_speech()` / flush loop 的实时持久化机制

## Decisions

### 1. Redis 连接管理：单例 + 连接池

**决策**: 使用 `redis.asyncio.Redis` 单例，预配置连接池（max_connections=10），在 FastAPI lifespan 中初始化/关闭。

**理由**: 
- `redis.asyncio` 与现有 `aiosqlite` + `asyncio` 模式一致
- 连接池避免每次操作建立新连接
- FastAPI lifespan 管理生命周期，与现有 `init_db()` / SSEBridge loop 模式一致

**备选**: 
- `redis-py` 同步客户端：需 `asyncio.to_thread` 包装，增加复杂度，不选
- `aioredis`：已弃用，不选

### 2. 缓存 Key 设计

```
debate:{debate_id}:speeches   → JSON array of speech objects (完整)
debate:{debate_id}:summary    → JSON array of speech summaries (不含 thinking)
```

**理由**: 
- 前缀 `debate:` 命名空间隔离
- 分离完整版和摘要版：列表页用摘要（体积小），回放用完整版
- 单 key 存储整个 speeches 数组（而非 HASH per speech），因为读取场景总是批量获取全部

**备选**: 
- Hash per speech (`debate:{id}:speech:{seq}`)：写入粒度细但不匹配读取模式（总是全量读），不选

### 3. 序列化格式：JSON

**决策**: 使用 `json.dumps` / `json.loads` 序列化 speech 对象列表。

**理由**: 
- speeches 数据量小（单场辩论通常 < 100 条，每条 < 5KB）
- JSON 人类可读，调试方便
- 与现有 API 响应格式一致

### 4. TTL 策略：24 小时

**决策**: 每个缓存 key 设置 `EXPIRE 86400`（24h）。

**理由**: 
- 辩论回放通常在完成后 24h 内查看
- 过期后自动回收，无需手动清理
- SQLite 始终为 source of truth，miss 时透明回退

### 5. 缓存写入时机

**决策**: 在 SSE 流结束时（`debate_end` 事件发送后）异步写入 Redis。在 main.py 的 `_run_debate` wrapper 中 `finally` 块写入。

**理由**: 
- 辩论结束是自然的写入点，避免中间态缓存
- `finally` 块确保即使异常退出也写入缓存
- 异步写入不阻塞 SSE 关闭流程

**备选**: 
- 每个 speech 实时写入：写入频率高、可能存储不完整数据，不选
- 定时批量写入：增加复杂度，不选

### 6. 前端预加载策略

**决策**: `loadHistory()` 在获取 `/api/debates` 后，并行调用 `GET /api/debate/speeches/batch?ids=id1,id2,...` 获取所有已完成辩论的 speeches 摘要。结果存入模块级 `speechCache` Map。

**理由**: 
- 一次批量请求替代 N 次单独请求，减少网络往返
- 前端内存缓存命中时，回放零延迟
- 摘要不含 thinking 内容，体积可控

**备选**: 
- 在 `/api/debates` 响应中直接包含 speeches：响应体过大，破坏现有 API 的轻量设计，不选
- 每个 debate item 单独请求：N 次请求增加延迟，不选

### 7. 缓存失效策略

**决策**: 
- 删除辩论时：`DELETE /api/debate/{id}` 同步删除 `debate:{id}:speeches` 和 `debate:{id}:summary`
- TTL 24h 兜底自动过期

**理由**: 简单直接，无分布式一致性问题。

## Risks / Trade-offs

- **[Risk] Redis 不可用时服务降级** → 所有 `redis_cache.get_speeches()` 调用 catch 异常后回退 SQLite，功能不受影响，仅性能退化
- **[Risk] 缓存与 DB 数据不一致** → 写入仅在辩论结束（终态）后发生，无中间态不一致问题；删除时同步清除。极端情况（Redis 写入失败）下次读取 miss 回退 SQLite
- **[Risk] 内存占用** → 单场辩论 speeches 约 100-200KB（完整版），Redis 中同时存完整+摘要两份。100 场辩论 ≈ 20-40MB，可接受
- **[Risk] 批量预加载增加首次页面加载时间** → 使用摘要版（不含 thinking），单场约 20-50KB。10 场辩论 ≈ 200-500KB。并行加载，增量渲染

## Migration Plan

1. 部署 Redis 服务（本地 `redis-server` 或 ECS Redis 实例）
2. 添加 `REDIS_URL` 环境变量到 `.env` 和 `deploy/debate.service`
3. 部署新代码：FastAPI lifespan 自动连接 Redis
4. 已有辩论的缓存为冷启动（miss → SQLite → 回填），无需数据迁移
5. 回滚：移除 Redis 依赖后，代码自动降级为纯 SQLite 模式

## Open Questions

- ECS 部署中 Redis 是使用 AWS ElastiCache 还是同机部署 `redis-server`？（由运维环境决定，代码层面通过 `REDIS_URL` 配置适配两者）
