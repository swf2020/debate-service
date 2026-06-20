# 新国辩赛制辩论系统 — 设计文档

## 概述

将现有 debate-service 从 3v3 通用赛制重构为 **新国辩（CDWC）标准赛制**：4 对 4 + 1 裁判，含双 Agent 交互质询，单轮制。彻底重写 `debate_flow.py`，废弃旧的多轮循环机制。

## 赛制对比

| 维度 | 旧赛制 (standard) | 新国辩 (cdwc) |
|------|------------------|--------------|
| 辩手 | 3 正 + 3 反 | 4 正 + 4 反 |
| 阶段数 | 10 | 11 |
| 质询 | 无 | 双 Agent 交互，最多 4 轮 |
| 轮次 | 1-3 轮可配 | 固定单轮 |
| 总结顺序 | 正方先 | 反方先 |

## 阶段链

```
pro_1_opening       → 正方一辩立论
con_1_opening       → 反方一辩立论
pro_2_rebuttal      → 正方二辩驳论
con_2_rebuttal      → 反方二辩驳论
pro_3_cross_examine → 正方三辩质询反方一/二辩（双Agent交互，最多4轮）
con_3_cross_examine → 反方三辩质询正方一/二辩（双Agent交互，最多4轮）
pro_3_summary       → 正方三辩质询小结
con_3_summary       → 反方三辩质询小结
free_debate         → 自由辩论（8人轮流，每方3次发言）
con_4_closing       → 反方四辩总结陈词（新国辩规则：反方先）
pro_4_closing       → 正方四辩总结陈词
judge_verdict       → 裁判评分与裁决
```

## Agent 角色设计（9 Agent）

| Agent | 角色 | 阶段职责 |
|-------|------|---------|
| pro_1 | 正方一辩 | 立论 |
| pro_2 | 正方二辩 | 驳论 |
| pro_3 | 正方三辩 | 质询反方一/二辩 + 质询小结 |
| pro_4 | 正方四辩 | 总结陈词 |
| con_1 | 反方一辩 | 立论 |
| con_2 | 反方二辩 | 驳论 |
| con_3 | 反方三辩 | 质询正方一/二辩 + 质询小结 |
| con_4 | 反方四辩 | 总结陈词 |
| judge | 裁判 | 综合评分 + 裁决 |

每个位置职责单一，不再复用（旧 pro_3 同时管论证+总结，现拆分给 pro_3/pro_4）。

## 质询阶段详细设计

### 流程

```python
cross_examine(examiner, targets, debate_state):
    round = 0
    while round < 4:
        round += 1
        q = examiner.ask(targets, history)    # 质询方提问
        push SSE cross_q_chunk
        persist speech (speech_type=cross_q)
        if q indicates end:                   # LLM 自主结束
            break
        a = target.answer(q, history)         # 被质询方回答
        push SSE cross_a_chunk
        persist speech (speech_type=cross_a)
```

### 约束
- 质询方与被质询方可多轮交互，最多 4 轮，超时强制截断
- LLM 可通过自然语言信号（如"感谢，质询到此结束"）自主终止
- 被质询方回答需简短有力（Prompt 约束），避免长篇大论
- 被质询方可为对方一辩或二辩，由质询方自主选择提问对象

## 自由辩论设计

- 8 人 round-robin：`(i % 4) + 1` 依次选 pro_n / con_n
- 每方 3 次发言机会，共 6 次交锋（pro → con → pro → con → pro → con）
- 不再嵌套 `while True` 多轮循环，单轮制

## 裁判评分

旧 4 维度 → 新 **5 维度**，新增"质询有效性"：

| 维度 | 分值 | 说明 |
|------|------|------|
| 论证严谨度 | 1-10 | 逻辑链条完整性 |
| 数据与事实支撑 | 1-10 | 论据充分性 |
| 反驳有效性 | 1-10 | 对对方论点的拆解 |
| 质询有效性 | 1-10 | 提问精准度 + 回答质量（新增） |
| 表达清晰度 | 1-10 | 语言组织能力 |

双方各 5 维度，满分 50 分。总分比较判定胜负，平局为 draw。

## 数据库变更

```sql
-- debates 表新增 format 字段
ALTER TABLE debates ADD COLUMN format TEXT NOT NULL DEFAULT 'cdwc';
-- 值: 'cdwc' | 'standard'

-- speeches 表新增 speech_type 字段
ALTER TABLE speeches ADD COLUMN speech_type TEXT NOT NULL DEFAULT 'opening';
-- 值: opening, rebuttal, cross_q, cross_a, cross_summary, free_debate, closing, verdict
```

- `total_rounds` 在 cdwc 模式恒为 1，保留字段兼容旧数据
- 旧 `standard` 格式通过 `format` 字段区分，不影响查询

## API 变更

`POST /api/debate/start` 新增 `format` 字段：

```json
{
    "topic": "人工智能是否威胁人类文明",
    "format": "cdwc",
    "rounds": 1,
    "pro_skills": {
        "debater_1": null, "debater_2": null,
        "debater_3": null, "debater_4": null
    },
    "con_skills": {
        "debater_1": null, "debater_2": null,
        "debater_3": null, "debater_4": null
    },
    "judge_skill": null
}
```

- `format` 默认 `"cdwc"`
- `rounds` 在 cdwc 模式忽略，固定单轮
- `pro_skills` / `con_skills` 键名改为 `debater_1` ~ `debater_4`
- 其余 API 路径不变

## SSE 事件新增

| 事件类型 | 载荷 | 说明 |
|---------|------|------|
| `cross_q_chunk` | `{examiner, target, content, round}` | 质询方提问 |
| `cross_a_chunk` | `{responder, content, round}` | 被质询方回答 |

## 前端设计

### 布局变更

3×2 → **4×2** 网格：

```
正方一辩 | 反方一辩
正方二辩 | 反方二辩
正方三辩 | 反方三辩
正方四辩 | 反方四辩
```

### 质询区

质询阶段弹出/展开独立面板：
- 左侧：提问方（高亮边框）
- 右侧：回答方
- 实时流式推送，回合编号分隔
- 非质询阶段隐藏

### 底部栏

- 移除轮次显示
- 改为 11 阶段进度条

### 裁判裁决区

- 5 维度得分表（新增"质询有效性"列）
- 总分 + 胜负判定 + 综合评语

## 实施策略

**彻底重写 `debate_flow.py`**，旧文件保留为 `debate_flow_standard.py`（如需兼容旧赛制）。新文件：

- `debate_flow.py` — CDWC Flow（新国辩）
- `debate_flow_standard.py` — 旧 3v3 Flow（如有需要）

## 关键文件改动

| 文件 | 改动 |
|------|------|
| `agents.py` | 新增 PRO_ROLES[4]/CON_ROLES[4]/JUDGE_ROLE；裁判评分 5 维度；质询 prompt 模板 |
| `debate_flow.py` | 彻底重写：11 阶段链 + cross_examine 方法 + 单轮自由辩论 |
| `models.py` | DebateState 加 format/cross_examine_target/cross_examine_round 字段 |
| `db.py` | migration: 加 format/speech_type 列 |
| `main.py` | StartDebateRequest 加 format 字段，路由分发到对应 Flow |
| `static/index.html` | 4×2 布局 + 质询面板 + 阶段进度条 + 5 维度裁决表 |

## 验证

1. `pytest -v` — 所有现有测试通过或适配
2. 启动服务，用 cdwc format 创建辩论
3. 确认 11 阶段顺序正确执行
4. 质询阶段验证：交互 ≤4 轮，LLM 自主结束生效
5. 前端：4×2 布局 + 质询面板实时更新
6. SSE 重连后 state snapshot 恢复完整状态
