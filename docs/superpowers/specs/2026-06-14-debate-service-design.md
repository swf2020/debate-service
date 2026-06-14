# 辩论 Agent 系统 — 设计文档

## 概述

基于 crewAI Flow 编排的多人辩论系统。正方 3 辩 vs 反方 3 辩，每个辩手可选挂载女娲蒸馏的人物 Skill，裁判综合评分裁决。前端 3 行 × 2 列实时展示，SSE 流式推送思考过程与发言内容。

## 技术栈

- **后端框架**: FastAPI + uvicorn
- **编排引擎**: crewAI Flow (DSL: @start / @listen)
- **LLM**: DeepSeek-v4-pro (OpenAI 兼容 API)
- **数据库**: SQLite (aiosqlite / sqlite3)
- **实时通信**: SSE (Server-Sent Events)
- **前端**: 原生 HTML/CSS/JS，零依赖
- **运行**: `python main.py`

## 项目结构

```
debate-service/
├── main.py              # FastAPI 入口，路由注册，SSE 端点
├── debate_flow.py       # crewAI Flow 定义（辩论流程编排）
├── debate_state.py      # Flow State 定义（轮次/发言/暂停标记）
├── agents.py            # 正方 3 辩 + 反方 3 辩 + 裁判 Agent 定义
├── sse_bridge.py        # crewAI 事件 → SSE 队列桥接
├── db.py                # SQLite 连接，建表，持久化操作
├── models.py            # Pydantic 请求/响应模型
├── skill_loader.py      # 女娲 Skill 文件读取与 Agent 注入
└── static/
    ├── index.html        # 单页面：辩题配置 + 实时辩论展示（CSS 内联）
    └── app.js            # SSE 连接 + UI 更新逻辑
```

## 数据库设计 (SQLite)

```sql
CREATE TABLE debates (
    id           TEXT PRIMARY KEY,       -- UUID
    topic        TEXT NOT NULL,
    total_rounds INT DEFAULT 2,
    status       TEXT DEFAULT 'running', -- running/paused/finished
    pro_skills   TEXT,                   -- JSON: {"debater_1":"munger","debater_2":null,"debater_3":null}
    con_skills   TEXT,                   -- JSON
    judge_skill  TEXT,
    winner       TEXT,                   -- pro/con/draw
    verdict      TEXT,                   -- JSON (scores + summary)
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at  DATETIME
);

CREATE TABLE speeches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    debate_id  TEXT NOT NULL,            -- FK debates.id
    debater    TEXT NOT NULL,            -- pro_1/pro_2/pro_3/con_1/con_2/con_3/judge
    phase      TEXT NOT NULL,            -- opening/rebuttal/argument/free_debate/closing/verdict
    round_num  INT NOT NULL,
    thinking   TEXT,                     -- 思考过程全文
    content    TEXT NOT NULL,            -- 发言内容全文
    seq        INT NOT NULL,             -- 发言序号（排序用）
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

持久化时机：
- 辩论创建：POST /start 时 INSERT debates
- 每次发言完成：Flow 阶段结束时 INSERT speeches
- 裁判裁决：UPDATE debates SET winner/verdict/finished_at
- 暂停/恢复：UPDATE debates SET status

## API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/debate/start` | 创建辩论，写入 DB，返回 debate_id，启动 Flow |
| GET  | `/api/debate/{id}/stream` | SSE 事件流 |
| POST | `/api/debate/{id}/pause` | 暂停辩论 |
| POST | `/api/debate/{id}/resume` | 恢复辩论 |
| GET  | `/api/debate/{id}` | 查询历史辩论详情（回放） |

### POST /api/debate/start 请求体

```json
{
    "topic": "人工智能是否威胁人类文明",
    "rounds": 2,
    "pro_skills": {
        "debater_1": "munger-perspective",
        "debater_2": null,
        "debater_3": null
    },
    "con_skills": {
        "debater_1": "taleb-perspective",
        "debater_2": null,
        "debater_3": null
    },
    "judge_skill": null
}
```

## SSE 事件类型

| 事件类型 | 载荷 | 说明 |
|---------|------|------|
| `phase_start` | `{phase, debater, round}` | 阶段开始 |
| `thinking_chunk` | `{debater, content}` | 辩手思考过程，流式，前端折叠灰暗字体 |
| `speech_chunk` | `{debater, content}` | 辩手发言内容，流式，前端黑色字体 |
| `phase_end` | `{phase, debater}` | 阶段结束，触发持久化 |
| `verdict_chunk` | `{content, scores}` | 裁判裁决，流式 |
| `paused` | `{}` | 辩论已暂停 |
| `resumed` | `{}` | 辩论已恢复 |
| `debate_end` | `{verdict}` | 辩论结束，含最终结果 |

## Flow 设计

### 辩论阶段（标准赛制，1-3 轮可配）

```
@start  begin_debate()
  |
@listen pro_1_opening() -> con_1_opening()       # 每轮：立论
  |
@listen pro_2_rebuttal() -> con_2_rebuttal()     # 每轮：驳论
  |
@listen pro_3_argument() -> con_3_argument()     # 每轮：深入论证
  |
@listen free_debate()                             # 每轮：自由辩论
  |                                               # 正反交替各发言 N 次，6 辩手均可参与
@listen check_next_round()                        # 若 current_round < total_rounds
  |                                               # current_round++，回到 pro_2_rebuttal
@listen pro_3_closing() -> con_3_closing()       # 总结陈词（仅三辩）
  |
@listen judge_verdict()                           # 裁判评分 + 裁决
```

### Flow State

```python
class DebateState(FlowState):
    topic: str
    total_rounds: int = 2
    current_round: int = 1
    current_phase: str
    pro_skills: dict       # {"debater_1": "munger", "debater_2": None, "debater_3": None}
    con_skills: dict
    judge_skill: str | None
    debate_history: list[dict]  # debater + content + phase
    paused: bool = False
    verdict: dict | None
```

### 暂停机制

每个阶段开始前检查 `state.paused`。若为 True，Flow 挂起等待。
- POST `/api/debate/{id}/pause` → 设置 paused=True
- POST `/api/debate/{id}/resume` → 清除标记，继续执行

## Agent 设计

### 6 辩手 + 1 裁判

| Agent | Role | 阶段职责 |
|-------|------|---------|
| pro_1 | 正方一辩 | 立论 |
| pro_2 | 正方二辩 | 驳论 |
| pro_3 | 正方三辩 | 深入论证、总结陈词 |
| con_1 | 反方一辩 | 立论 |
| con_2 | 反方二辩 | 驳论 |
| con_3 | 反方三辩 | 深入论证、总结陈词 |
| judge | 裁判 | 综合评分 + 裁决 |

自由辩论阶段：正方先发言 → 反方回应，交替进行（每方每轮 2-3 次发言机会），任意辩手可代表本方发言。由 Flow 内循环控制交替节奏。

### Skill 加载机制

每个 Agent 可选挂载一个女娲蒸馏的人物 Skill（`.claude/skills/{name}-perspective/SKILL.md`）。Skill 提供该人物的心智模型、决策启发式、表达 DNA，注入到 Agent 的 backstory 中。

```python
def build_agent_with_skill(role, goal, default_backstory, skill_path=None):
    backstory = default_backstory
    if skill_path and os.path.exists(skill_path):
        skill_content = read_file(skill_path)
        backstory += f"\n\n## 你的思维框架\n{skill_content}"
    return Agent(role=role, goal=goal, backstory=backstory, llm=llm, ...)
```

若未指定 Skill，使用默认辩手人设。Skill 列表从 `.claude/skills/` 目录自动扫描所有 `*-perspective/`。

### 裁判评分维度

| 维度 | 分值 |
|------|------|
| 论证严谨度 | 1-10 |
| 数据与事实支撑 | 1-10 |
| 反驳有效性 | 1-10 |
| 表达清晰度 | 1-10 |

双方各 4 维度，满分 40 分。总分比较判定胜负，平局为 draw。

### 思考与发言分离

采用双阶段 Prompt：Agent 先内部推理（thinking_chunk），再生成正式发言（speech_chunk）。利用 crewAI callback 机制区分 LLM reasoning 输出与最终输出，分别推送不同 SSE 事件。

## 前端设计

### 配置面板

每项独立一行，左右对齐：
- 辩题（输入框）
- 轮次（下拉框 1/2/3）
- 正方 Skill（一辩/二辩/三辩 下拉框）
- 反方 Skill（一辩/二辩/三辩 下拉框）
- 裁判 Skill（下拉框）
- 开始辩论按钮（与上方控件左对齐）

### 辩论展示：3 行 × 2 列

```
正方一辩 | 反方一辩
正方二辩 | 反方二辩
正方三辩 | 反方三辩
```

- 当前发言者高亮（边框变色 + 状态标签）
- 思考过程：折叠（details/summary），灰暗字体，SSE 流式
- 发言内容：黑色字体，SSE 流式
- 其他辩手：显示历史发言
- 底部控制栏：当前轮次/阶段 + 暂停/恢复按钮

### 裁判裁决区

辩论结束后展示：
- 双方各维度得分 + 总分
- 胜负判定
- 裁判综合评语

## 错误处理

- LLM 调用失败：重试 1 次，仍失败则标记该阶段异常，SSE 推送 error 事件，继续下一阶段
- Skill 文件不存在：回退默认人设，记录警告
- 前端断连：辩论继续执行，重新连接 SSE 时推送当前状态快照

## 非功能需求

- 首字节时间：辩论开始后 < 3s 收到第一个 SSE 事件
- 并发：支持至少 3 场辩论同时进行
- 持久化：所有发言在阶段结束时写入 SQLite
