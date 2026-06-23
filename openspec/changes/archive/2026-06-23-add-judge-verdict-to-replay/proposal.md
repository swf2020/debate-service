## Why

辩论回放（reconnect SSE / history_replay / GET /api/debate/{id}）只缓存 speeches 到 Redis，裁判判决（verdict）不会随 `history_replay` 事件下发。已完成辩论的回放页面必须额外调用 REST API 才能渲染判决，导致回放体验不完整。需将 verdict 纳入 Redis 缓存和 `SSEHistoryReplay` 事件，确保判决在回放时即时可用。

## What Changes

- Redis 缓存层新增 `cache_verdict()` / `get_verdict()` 方法，辩论结束时缓存判决
- `SSEHistoryReplay` 模型新增 `verdict` 和 `winner` 字段
- `main.py` 重连 SSE 路径：从 Redis/DB 读取 verdict 并填入 `SSEHistoryReplay`
- `GET /api/debate/{id}` 端点：优先 Redis 读取 verdict，miss 回退 SQLite
- 前端 `debate.js` `history_replay` 处理：直接渲染 verdict（无需额外 API 调用）
- 删除辩论时同步清除 Redis 中的 verdict 缓存
- **BREAKING**: 无破坏性变更，所有现有 API 保持兼容

## Capabilities

### New Capabilities
- `verdict-cache`: Redis 判决缓存，存储/读取/失效策略，与 speech cache 共享 TTL（24h）
- `verdict-replay`: 回放时判决下发，确保 `history_replay` SSE 事件包含 verdict 字段

### Modified Capabilities
- `redis-cache`: 新增 `cache_verdict` / `get_verdict` 方法，扩展 `invalidate_debate` 同时清除 verdict 键
- `speech-preload`: 预加载逻辑不变，但 `history_replay` 路径新增 verdict 字段填充

## Impact

- **后端文件**: `redis_cache.py`（新增 verdict 方法）、`models.py`（`SSEHistoryReplay` 加字段）、`main.py`（SSE 重连路径 + REST 端点读 verdict）
- **前端文件**: `debate.js`（`history_replay` 分支渲染 verdict）、`ui.js`（`showVerdict` 已支持，无需改动）
- **依赖**: 无新增依赖
- **部署**: 无变更，Redis 已部署
