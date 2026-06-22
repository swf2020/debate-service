## Why

辩论首页（历史列表页）仅展示元数据（topic/status/winner），演讲内容需点击"查看回放"后才通过 `GET /api/debate/{id}` 从 SQLite 加载，导致回放页面有明显的加载延迟。同时，每次请求都直接查询 SQLite，无任何缓存层，高并发下数据库压力大。引入 Redis 缓存辩论演讲数据，并在首页预加载演讲内容，可消除回放等待时间并降低数据库负载。

## What Changes

- 新增 Redis 连接管理模块，支持连接池和健康检查
- 辩论结束时自动将 speeches 写入 Redis 缓存（TTL 24h）
- 新增 `GET /api/debate/{id}/speeches` 端点，优先从 Redis 读取，miss 时回退 SQLite 并回填缓存
- 辩论历史列表页加载时，批量预加载所有已完成辩论的 speeches 到前端（新增轻量级 speeches 摘要字段，不含完整 thinking 内容以控制体积）
- 前端 `history.js` 在 `loadHistory()` 时并发获取所有辩论的 speeches 摘要，本地缓存到内存
- 点击"查看回放"时优先使用前端内存缓存，命中即即时渲染，未命中才请求 API
- 删除辩论时同步清除 Redis 缓存
- **BREAKING**: 无破坏性变更，所有现有 API 保持兼容

## Capabilities

### New Capabilities
- `redis-cache`: Redis 缓存层，管理连接池、序列化/反序列化、TTL 过期、缓存失效策略
- `speech-preload`: 辩论首页演讲预加载，前端内存缓存 + 后端批量 API，消除回放加载延迟

### Modified Capabilities
<!-- 无现有 spec 需要修改 -->

## Impact

- **依赖**: 新增 `redis` (Python redis client) 和 `hiredis` 依赖；需运行 Redis 服务（本地或远程）
- **配置**: `.env` 新增 `REDIS_URL` 环境变量（默认 `redis://localhost:6379/0`）
- **后端文件**: `main.py`（新增 speeches 端点、Redis 生命周期管理）、`db.py`（保持现有查询不变）、新增 `redis_cache.py`
- **前端文件**: `history.js`（预加载逻辑）、`debate.js`（内存缓存优先）、`api.js`（新增 API 调用）
- **部署**: `deploy/debate.service` 需确保 Redis 服务先于应用启动；ECS 部署需配置 Redis 实例
