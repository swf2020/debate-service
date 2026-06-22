## 1. Redis 缓存模块（后端基础设施）

- [ ] 1.1 添加 `redis` 和 `hiredis` 到 `requirements.txt`
- [ ] 1.2 创建 `redis_cache.py`：`RedisCache` 类，含连接池初始化、`get_redis()` 单例、`close()` 方法
- [ ] 1.3 实现 `cache_speeches(debate_id, speeches)` — 写入完整版 + 摘要版到 Redis，TTL 86400s
- [ ] 1.4 实现 `get_speeches(debate_id)` — 优先从 Redis 读取完整版，miss 返回 None（调用方回退 SQLite）
- [ ] 1.5 实现 `get_speeches_summary(debate_id)` — 优先从 Redis 读取摘要版，miss 返回 None
- [ ] 1.6 实现 `get_batch_summaries(debate_ids: list[str])` — 批量获取摘要，pipeline 优化，分别标记 hit/miss
- [ ] 1.7 实现 `invalidate_debate(debate_id)` — 删除 `debate:{id}:speeches` 和 `debate:{id}:summary`
- [ ] 1.8 在 FastAPI lifespan 中初始化/关闭 Redis 连接（main.py `lifespan` 函数）
- [ ] 1.9 编写 `test_redis_cache.py` 单元测试（mock redis client，验证缓存读写、miss 回退、失效逻辑）

## 2. 后端 API 改造

- [ ] 2.1 新增 `GET /api/debate/speeches/batch?ids=...` 端点，调用 `get_batch_summaries()`，miss 部分从 SQLite 查询并回填缓存
- [ ] 2.2 改造 `GET /api/debate/{id}` 端点，speeches 读取优先走 Redis，miss 时回退 `get_speeches()` + 异步回填
- [ ] 2.3 改造 `DELETE /api/debate/{id}` 端点，删除 DB 记录后同步调用 `invalidate_debate()`
- [ ] 2.4 在 `_run_debate()` 的 `finally` 块中添加 `cache_speeches()` 调用（辩论结束/异常时自动缓存）
- [ ] 2.5 编写 `test_debate_api_cache.py` 集成测试（验证 batch 端点、缓存命中/未命中、删除清除缓存）

## 3. 前端预加载与内存缓存

- [ ] 3.1 在 `api.js` 添加 `fetchBatchSpeeches(ids)` 函数，调用 `GET /api/debate/speeches/batch?ids=...`
- [ ] 3.2 在 `debate.js` 中添加模块级 `speechCache` (Map) 及 `getCachedSpeeches(id)` / `setCachedSpeeches(id, data)` / `clearCachedSpeeches(id)` 函数
- [ ] 3.3 改造 `history.js` 的 `loadHistory()`，获取辩论列表后提取所有已完成辩论的 ID，调用 `fetchBatchSpeeches()` 并存入 `speechCache`
- [ ] 3.4 改造 `debate.js` 的 `enterDebate()`，finished 状态优先检查 `speechCache`，命中则直接用缓存数据调用 `restoreSpeeches()`，未命中才请求 `GET /api/debate/{id}`
- [ ] 3.5 改造 `history.js` 删除辩论处理，删除成功后调用 `clearCachedSpeeches(id)` 清理前端缓存
- [ ] 3.6 在 `debate.js` 中添加加载状态：网络请求时显示 spinner（`#debate-grid` 内添加 loading overlay），缓存命中时无加载状态
- [ ] 3.7 编写 `static/js/__tests__/speech-cache.test.js`（vitest，验证缓存命中/未命中/清除逻辑）

## 4. 部署配置

- [ ] 4.1 在 `.env` 添加 `REDIS_URL=redis://localhost:6379/0` 配置项
- [ ] 4.2 在 `deploy/debate.service` 添加 `Environment=REDIS_URL=...` 和 Redis 启动依赖（`After=redis.service`）
- [ ] 4.3 在 `deploy/setup.sh` 添加 Redis 安装检查逻辑
