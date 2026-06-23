## 1. 心跳检测基础设施

- [x] 1.1 在 `debate.js` 中新增 `startHeartbeat()` 函数：每 5 秒 ping `/api/debate/active`，连续 3 次失败触发自动暂停
- [x] 1.2 新增 `stopHeartbeat()` 函数：清除心跳定时器，重置失败计数器和 `autoPaused` 标志
- [x] 1.3 编写 `heartbeat` 模块的 vitest 单元测试：测试计数器递增、重置、连续失败触发回调

## 2. 网络断连自动暂停

- [x] 2.1 实现 `onNetworkLost()` 回调：设置 `autoPaused=true`，调用 `POST /api/debate/{id}/pause`，显示 Toast "网络中断，辩论已自动暂停"
- [x] 2.2 增强 SSE `onerror` 处理：心跳间隔缩短为 2 秒加速确认断连
- [x] 2.3 编写自动暂停流程的单元测试：mock fetch 模拟连续失败，验证 pause API 被调用且仅调用一次

## 3. 网络恢复与重连

- [x] 3.1 实现 `onNetworkRecovered()` 回调：重连 SSE（不 resume），显示 Toast "网络已恢复"
- [x] 3.2 网络恢复后重置 `autoPaused=false`，心跳恢复 5 秒间隔
- [x] 3.3 编写网络恢复流程的单元测试：验证 SSE 重连和 Toast 显示

## 4. 生命周期集成

- [x] 4.1 `startDebate()` 成功后启动心跳定时器
- [x] 4.2 `enterDebate()` 运行中辩论时启动心跳定时器
- [x] 4.3 `debate_end` SSE 事件处理中停止心跳
- [x] 4.4 `backToList()` / `resetToNewDebate()` 中停止心跳
- [x] 4.5 编写生命周期集成的单元测试

## 5. 验证

- [x] 5.1 `npx vitest run` 全部测试通过（129 tests, 10 files）
- [x] 5.2 `pytest -v` 回归通过（240 passed, 2 pre-existing failures unrelated）
- [ ] 5.3 浏览器验证：开始辩论 → 断开 WiFi → 确认自动暂停 Toast 出现 → 恢复 WiFi → 确认恢复 Toast 出现
