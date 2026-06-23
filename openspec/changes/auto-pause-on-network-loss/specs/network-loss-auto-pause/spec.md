## ADDED Requirements

### Requirement: Heartbeat-based network loss detection
系统 SHALL 在辩论进行中通过定时心跳检测网络连通性。心跳间隔为 5 秒，连续 3 次失败后判定网络中断。

#### Scenario: Heartbeat succeeds during normal operation
- **WHEN** 辩论正在进行且心跳请求收到 200 响应
- **THEN** 失败计数器重置为 0，系统保持正常运行

#### Scenario: Three consecutive heartbeat failures trigger auto-pause
- **WHEN** 心跳请求连续 3 次失败（超时或非 2xx 响应）
- **THEN** 系统自动调用 `POST /api/debate/{id}/pause`，显示 Toast "网络中断，辩论已自动暂停"

#### Scenario: Heartbeat not started when no debate running
- **WHEN** 用户在配置页面且无进行中的辩论
- **THEN** 不启动心跳定时器

### Requirement: SSE error triggers network loss detection
系统 SHALL 在 SSE EventSource 触发 `onerror` 时加快心跳检测频率至 2 秒间隔。

#### Scenario: SSE onerror accelerates heartbeat
- **WHEN** EventSource 触发 onerror 事件
- **THEN** 心跳间隔缩短为 2 秒，直到连通性恢复或确认断连

### Requirement: Auto-pause idempotency
系统 SHALL 通过 `autoPaused` 标志防止重复自动暂停调用。

#### Scenario: Duplicate pause prevented
- **WHEN** 网络已被检测为中断且 autoPaused 为 true
- **THEN** 后续心跳失败不会再次调用 pause API

#### Scenario: Auto-pause re-enabled after reconnect
- **WHEN** 网络恢复后 SSE 重连成功
- **THEN** autoPaused 重置为 false，恢复断连检测能力

### Requirement: Network recovery detection
系统 SHALL 在自动暂停后继续发送心跳（间隔 5 秒），检测网络恢复。

#### Scenario: Network recovery detected
- **WHEN** 自动暂停后心跳请求首次成功（200 响应）
- **THEN** 系统重连 SSE（不自动 resume 辩论），显示 Toast "网络已恢复"

#### Scenario: Manual resume after network recovery
- **WHEN** 网络恢复后 SSE 重连成功且 `history_replay` 显示 paused 状态
- **THEN** 用户可点击 "恢复辩论" 按钮手动继续

### Requirement: Heartbeat lifecycle management
系统 SHALL 在辩论生命周期变化时正确管理心跳定时器。

#### Scenario: Heartbeat started on debate start
- **WHEN** `startDebate()` 成功创建辩论并获得 debate_id
- **THEN** 启动心跳定时器

#### Scenario: Heartbeat stopped on debate end
- **WHEN** 收到 `debate_end` SSE 事件
- **THEN** 清除心跳定时器

#### Scenario: Heartbeat stopped on back to list
- **WHEN** 用户点击返回列表
- **THEN** 清除心跳定时器，停止网络检测
