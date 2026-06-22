## 1. Redis 缓存层 — verdict 方法

- [x] 1.1 编写 `test_redis_verdict_cache.py`：测试 `cache_verdict` / `get_verdict` / `invalidate_debate` / `get_batch_verdicts` 四个方法，覆盖命中、未命中、Redis 不可用降级场景
- [x] 1.2 在 `redis_cache.py` 中实现 `cache_verdict(debate_id, verdict, winner)` 方法，键 `debate:{id}:verdict`，TTL 24h
- [x] 1.3 在 `redis_cache.py` 中实现 `get_verdict(debate_id) -> dict | None` 方法
- [x] 1.4 在 `redis_cache.py` 中实现 `get_batch_verdicts(debate_ids) -> dict[str, dict] | None` 方法
- [x] 1.5 扩展 `invalidate_debate(debate_id)` 同时删除 verdict 键

## 2. 数据模型 — SSEHistoryReplay 扩展

- [x] 2.1 编写 `test_models_verdict_replay.py`：验证 `SSEHistoryReplay` 序列化/反序列化时 `verdict` 和 `winner` 字段正确传递
- [x] 2.2 在 `models.py` 的 `SSEHistoryReplay` 中新增 `verdict: dict | None = None` 和 `winner: str | None = None` 字段

## 3. 后端 SSE 重连路径 — verdict 下发

- [x] 3.1 编写 `test_main_verdict_replay.py`：测试 SSE 重连时 `history_replay` 事件包含 verdict（finished 状态）和不包含 verdict（running 状态）两种情况
- [x] 3.2 在 `main.py` 的 `GET /api/debate/{id}/stream` 活跃流路径（约 349 行）中：从 `flow.state` 读取 verdict 填入 `SSEHistoryReplay`
- [x] 3.3 在 `main.py` 的 `GET /api/debate/{id}/stream` 数据库路径（约 385 行）中：先从 `cache.get_verdict()` 读，miss 则从 `get_debate()` 读取并回填缓存
- [x] 3.4 在 `main.py` 的 `GET /api/debate/{id}` REST 端点中：优先从 `cache.get_verdict()` 读 verdict

## 4. 辩论结束 — verdict 写入缓存

- [x] 4.1 编写 `test_debate_flow_verdict_cache.py`：验证 `judge_verdict()` 阶段结束时 verdict 被写入 Redis
- [x] 4.2 在 `debate_flow.py` 的 `judge_verdict()` 方法中：`set_verdict` 调用后追加 `cache.cache_verdict(debate_id, verdict, winner)`
- [x] 4.3 在 `debate_flow_standard.py` 的 `judge_verdict()` 方法中：同样追加 `cache.cache_verdict`

## 5. 前端 — history_replay 渲染 verdict

- [x] 5.1 编写 `static/js/__tests__/verdict-replay.test.js`：模拟 `history_replay` 事件携带 verdict 时调用 `showVerdict`，不携带时不调用
- [x] 5.2 更新 `static/js/debate.js` 的 `history_replay` 分支（约 286 行）：检查 `msg.verdict` 和 `msg.status === 'finished'`，满足条件时调用 `showVerdict(msg.verdict, msg.winner)`（已有代码，无需修改）
- [x] 5.3 确保 `history_replay` 渲染 verdict 时 DOM 结构存在（`ui.js` 的 `showVerdict` 已支持，仅需验证）

## 6. 集成验证

- [x] 6.1 编写端到端测试：完整辩论 → 结束 → SSE 重连 → 验证 `history_replay` 包含 verdict
- [x] 6.2 运行全部已有测试，确保无回归（`pytest -v` + `npx vitest run`）
