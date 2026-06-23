## Why

辩论进行中如果用户网络中断（WiFi断开、移动网络切换），前端SSE连接断开但后端继续运行，导致辩手发言内容丢失、状态不同步。需要在检测到网络中断时自动暂停辩论，保护发言内容不丢失。

## What Changes

- 前端新增网络心跳检测机制（SSE连接状态 + navigator.onLine + 定时ping）
- 检测到网络中断后自动调用 `POST /api/debate/{id}/pause` 暂停辩论
- 网络恢复后自动重连SSE，恢复辩论状态展示
- 前端Toast提示用户网络中断/恢复状态
- 暂停成功后，后端可继续完成当前发言再暂停（利用现有pause机制：轮询 `self.state.paused` 在 phase 结束后生效）

## Capabilities

### New Capabilities

- `network-loss-auto-pause`: 前端检测网络中断后自动暂停辩论，网络恢复后自动重连

### Modified Capabilities

<!-- No existing capabilities modified -->

## Impact

- `static/js/debate.js`: 新增网络检测逻辑（EventSource error handler + navigator.onLine + heartbeat）
- `static/js/api.js`: 可能需要新增轻量级ping端点
- `main.py`: 可选新增 `/api/ping` 或复用现有端点做心跳检测
