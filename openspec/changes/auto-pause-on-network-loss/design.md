## Context

当前辩论系统依赖 SSE 单向推送，前端无心跳检测。SSE 连接断开时（WiFi断开、网络切换），EventSource 的 `onerror` 触发但前端不会主动暂停辩论，后端继续运行。用户可能丢失几分钟的发言内容。

后端已有完整的 pause/resume 机制（`flow.state.paused` 标志 + `_check_pause()` 轮询），只需前端在检测到断连时调用 `POST /api/debate/{id}/pause`。

## Goals / Non-Goals

**Goals:**
- 前端检测 SSE 连接中断（网络断开/超时）后自动暂停辩论
- 网络恢复后自动重连 SSE，恢复辩论状态
- Toast 提示用户网络状态变化
- 支持手动恢复（resume 按钮仍可用）

**Non-Goals:**
- 不改变后端 pause/resume 逻辑
- 不处理服务端崩溃场景（后端重启已有 on_start 状态恢复逻辑）
- 不处理长时间离线后辩论已结束的场景（重连时 `history_replay` 会覆盖状态）

## Decisions

### 1. 检测方式：SSE onerror + 心跳保活

**选择**: 复用现有 `GET /api/debate/active` 作为心跳 ping 端点（返回 200/401 即可，忽略响应体），速率 5s 一次。连续 3 次失败判定为断连。

**备选方案**:
- 新增 `/api/ping` 端点：更轻量，但需要改后端。废弃原因：`/api/debate/active` 已有 auth 校验，延迟可忽略。
- 仅依赖 `navigator.onLine`：不可靠，`onLine=true` 不代表能连通服务器。
- 仅依赖 EventSource `onerror`：浏览器重连机制会掩盖短暂断连，不触发 error。

**判定逻辑**: SSE `onerror` 或心跳连续失败 3 次（15s 窗口）→ 触发自动暂停。navigator.onLine 仅用于快速排除（`onLine=false` 时直接标记疑似断连，缩短心跳检测间隔到 2s）。

### 2. 暂停动作：防重入 + 幂等调用

`POST /api/debate/{id}/pause` 本身幂等（重复暂停无副作用）。前端加 `autoPaused` 标志防止重复调用。

```
网络断连检测 → autoPaused=true → POST /pause → showToast("网络中断，辩论已自动暂停")
网络恢复检测 → 重连 SSE (history_replay 恢复状态) → autoPaused=false → showToast("网络已恢复")
```

### 3. 恢复：SSE 重连 + history_replay

重连不直接 resume 辩论，由用户手动恢复（或后续可加自动恢复选项）。重连 SSE 后 `history_replay` 事件会恢复所有 speeches 和 debater_status，前端回到一致状态。

### 4. 生命周期管理

心跳定时器和 SSE 连接随 `currentDebateId` 生命周期：
- `startDebate()` / `enterDebate()` 时启动心跳
- `backToList()` / `resetToNewDebate()` / `debate_end` 时停止心跳
- 暂停期间心跳继续（因未结束辩论，需要检测何时网络恢复）

## Risks / Trade-offs

- **[R] 心跳频率过高浪费带宽** → 5s 间隔 + 仅在辩论进行中启用心跳，配置页不启动
- **[R] 网络抖动误触发自动暂停** → 连续 3 次失败才触发（15s 容忍窗口），避免单次超时误判
- **[R] 后端暂停有延迟** → `_check_pause()` 在当前 phase 结束后才真正暂停，最多延迟一个 phase 时长。这是设计取舍：不中断正在进行的发言
- **[R] 心跳请求增加服务端负载** → 频率 5s 一次，单用户负载可忽略；多用户时轻量查询端点影响小
