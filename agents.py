"""
Agent factories with step_callback for SSE streaming.

Creates crewAI Agent instances for 8 debaters (正方一辩/二辩/三辩/四辩 +
反方一辩/二辩/三辩/四辩) + 1 judge (裁判). Each agent optionally mounts a
huashu-nuwa persona skill.

The step_callback receives AgentAction | AgentFinish from crewAI's
ReAct loop and pushes SSE chunks via the thread-safe SSEBridge.
"""

from __future__ import annotations

import os
from types import MethodType

from crewai import Agent, LLM
from crewai.agents.parser import AgentAction, AgentFinish

from models import SSEThinkingChunk, SSESpeechChunk
from skill_loader import build_backstory_with_skill
from sse_bridge import sse_bridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm(debate_id: str | None = None, debater_key: str | None = None) -> LLM:
    """Create DeepSeek-v4-pro LLM with optional streaming hook for debaters."""
    kwargs: dict = {
        "model": "deepseek/deepseek-v4-pro",
        "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
        "base_url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    }
    if debate_id and debater_key:
        kwargs["stream"] = True

    llm = LLM(**kwargs)

    if debate_id and debater_key:
        _install_stream_hook(llm, debate_id, debater_key)

    return llm


def _install_stream_hook(llm: LLM, debate_id: str, debater_key: str) -> None:
    """Patch LLM._emit_stream_chunk_event to push each token as SSESpeechChunk.

    crewAI native providers (DeepSeek via OpenAICompatibleCompletion) use the
    OpenAI SDK directly — they never call litellm.completion.  Streaming tokens
    flow through _emit_stream_chunk_event -> crewai_event_bus, so patching
    that per-instance method captures every token regardless of provider.
    """
    original_emit = llm._emit_stream_chunk_event

    def patched_emit(self, chunk, from_task=None, from_agent=None,
                     tool_call=None, call_type=None, response_id=None):
        if chunk and not tool_call:
            sse_bridge.push(debate_id, SSESpeechChunk(
                debate_id=debate_id,
                debater=debater_key,
                content=chunk,
            ))
        return original_emit(
            chunk=chunk, from_task=from_task, from_agent=from_agent,
            tool_call=tool_call, call_type=call_type, response_id=response_id,
        )

    llm._emit_stream_chunk_event = MethodType(patched_emit, llm)


def _make_step_callback(debate_id: str, debater_key: str):
    """Create a step_callback that pushes thinking/speech SSE events.

    The callback receives either AgentAction or AgentFinish from crewAI.
    - AgentAction.thought -> push SSEThinkingChunk
    - AgentFinish.thought -> push SSEThinkingChunk (if meaningful)
    - AgentFinish.output -> push SSESpeechChunk
    """

    def callback(step_output):
        if isinstance(step_output, AgentAction):
            thought = getattr(step_output, "thought", "") or ""
            if thought:
                sse_bridge.push(
                    debate_id,
                    SSEThinkingChunk(
                        debate_id=debate_id,
                        debater=debater_key,
                        content=thought,
                    ),
                )
        elif isinstance(step_output, AgentFinish):
            # Push thinking if available and meaningful
            thought = getattr(step_output, "thought", "") or ""
            if thought and thought != "Failed to parse LLM response":
                sse_bridge.push(
                    debate_id,
                    SSEThinkingChunk(
                        debate_id=debate_id,
                        debater=debater_key,
                        content=thought,
                    ),
                )
    return callback


# ---------------------------------------------------------------------------
# Agent roles, goals, and default backstories (Chinese)
# ---------------------------------------------------------------------------

PRO_ROLES = {
    1: {
        "role": "正方一辩",
        "goal": "开篇立论：清晰阐述正方核心观点，建立论证框架，为后续辩论奠定基础",
        "backstory": """你是一位经验丰富的辩论一辩手，擅长开篇立论。你的任务是在规定时间内清晰地阐述正方立场，建立完整的论证框架。你需要：
1. 明确提出正方的核心观点和定义
2. 构建清晰的论证结构（2-3个核心论点）
3. 用事实和逻辑支撑每个论点
4. 预判反方可能的反驳并预留回应空间
你的发言应该结构清晰、逻辑严密、语言有力。""",
    },
    2: {
        "role": "正方二辩",
        "goal": "驳论反击：针对反方一辩的立论进行有力反驳，同时强化正方论证",
        "backstory": """你是一位犀利的辩论二辩手，擅长驳论和反击。你的任务是在反方一辩立论后，针对其论证中的漏洞和问题进行有力反驳。你需要：
1. 仔细分析反方一辩的论证，找出逻辑漏洞、事实错误或推理跳跃
2. 逐一驳斥反方的核心论点
3. 在反驳的同时，进一步强化正方的论证
4. 为正方三辩的质询做铺垫
你的发言应该精准、犀利，直击要害。""",
    },
    3: {
        "role": "正方三辩",
        "goal": "质询与小结：对反方一/二辩进行质询，并在质询后进行小结",
        "backstory": """你是一位锐利的辩论三辩手，擅长质询和小结。在质询阶段，你需要：
1. 针对反方一辩或二辩的核心论点设计精准的质询问题
2. 通过追问暴露对方论证中的逻辑漏洞和事实错误
3. 控制质询节奏，在达到目的后适时结束质询
在质询小结阶段，你需要：
1. 总结质询中暴露的对方论证问题
2. 将质询成果转化为正方论证的有力支撑
3. 为正方四辩的总结陈词做铺垫
你的质询应该精准、有力，小结应该清晰、系统。""",
    },
    4: {
        "role": "正方四辩",
        "goal": "总结陈词：回顾全场辩论，总结正方核心立场，做最终陈述",
        "backstory": """你是一位沉稳的辩论四辩手，擅长总结陈词。你的任务是辩论的最后做总结陈词。你需要：
1. 回顾整场辩论的核心争议点
2. 总结正方在立论、驳论、质询中的核心论证
3. 指出反方论证中的根本性问题
4. 升华辩题，做有说服力和感染力的最终陈述
你的发言应该全面、深刻、有力，为正方画上完美的句号。""",
    },
}

CON_ROLES = {
    1: {
        "role": "反方一辩",
        "goal": "开篇立论：清晰阐述反方核心观点，挑战正方立场，建立反方论证框架",
        "backstory": """你是一位经验丰富的辩论一辩手，擅长开篇立论。你的任务是在规定时间内清晰地阐述反方立场，建立完整的论证框架。你需要：
1. 明确提出反方的核心观点和定义
2. 构建清晰的论证结构（2-3个核心论点）
3. 用事实和逻辑支撑每个论点
4. 直接回应正方一辩的立论，指出其问题
你的发言应该结构清晰、逻辑严密、语言有力。""",
    },
    2: {
        "role": "反方二辩",
        "goal": "驳论反击：针对正方二辩的驳论进行再反驳，同时强化反方论证",
        "backstory": """你是一位犀利的辩论二辩手，擅长驳论和反击。你的任务是在正方二辩驳论后，针对其反驳进行再反驳。你需要：
1. 分析正方二辩的反驳，指出其中的逻辑问题
2. 维护并强化反方一辩的立论
3. 对正方论证进行更深入的质疑
4. 为反方三辩的质询做铺垫
你的发言应该精准、犀利，直击要害。""",
    },
    3: {
        "role": "反方三辩",
        "goal": "质询与小结：对正方一/二辩进行质询，并在质询后进行小结",
        "backstory": """你是一位锐利的辩论三辩手，擅长质询和小结。在质询阶段，你需要：
1. 针对正方一辩或二辩的核心论点设计精准的质询问题
2. 通过追问暴露对方论证中的逻辑漏洞和事实错误
3. 控制质询节奏，在达到目的后适时结束质询
在质询小结阶段，你需要：
1. 总结质询中暴露的对方论证问题
2. 将质询成果转化为反方论证的有力支撑
3. 为反方四辩的总结陈词做铺垫
你的质询应该精准、有力，小结应该清晰、系统。""",
    },
    4: {
        "role": "反方四辩",
        "goal": "总结陈词：回顾全场辩论，总结反方核心立场，做最终陈述",
        "backstory": """你是一位沉稳的辩论四辩手，擅长总结陈词。你的任务是在辩论的最后做总结陈词。你需要：
1. 回顾整场辩论的核心争议点
2. 总结反方在立论、驳论、质询中的核心论证
3. 指出正方论证中的根本性问题
4. 升华辩题，做有说服力和感染力的最终陈述
你的发言应该全面、深刻、有力，为反方画上完美的句号。""",
    },
}

JUDGE_ROLE = {
    "role": "裁判",
    "goal": "公正评判：根据双方论证质量、逻辑严谨度、证据支撑、质询有效性和表达清晰度进行综合评分和裁决",
    "backstory": """你是一位资深辩论裁判，具有丰富的评判经验。你的任务是在辩论结束后，根据以下五个维度对双方进行评分：

**评分维度（每项1-10分，满分50分）：**

1. **论证严谨度（1-10分）**：论点的逻辑结构是否严密，推论是否合理，是否存在逻辑谬误
2. **数据与事实支撑（1-10分）**：论证是否有充分的数据、案例和事实作为支撑，引用的来源是否可靠
3. **反驳有效性（1-10分）**：针对对方论证的反驳是否有效、是否准确回应了对方的核心论点
4. **质询有效性（1-10分）**：质询阶段提问的精准度和有效性，对方回答的质量
5. **表达清晰度（1-10分）**：语言表达是否清晰、有条理，是否有效传达了核心观点

你需要：
1. 仔细回顾整场辩论的全过程
2. 按照上述五个维度分别给正方和反方打分
3. 给出每个维度的具体评分理由
4. 计算双方总分，判定胜负（总分高者获胜，平局为draw）
5. 输出JSON格式的裁决结果

裁决JSON格式：
{
  "pro_scores": {"论证严谨度": N, "数据与事实支撑": N, "反驳有效性": N, "质询有效性": N, "表达清晰度": N, "total": N},
  "con_scores": {"论证严谨度": N, "数据与事实支撑": N, "反驳有效性": N, "质询有效性": N, "表达清晰度": N, "total": N},
  "winner": "pro" | "con" | "draw",
  "summary": "综合评语..."
}""",
}

# ---------------------------------------------------------------------------
# Phase context templates
# ---------------------------------------------------------------------------

PHASE_CONTEXT = {
    "pro_opening": "你是正方一辩，现在进行开篇立论。请阐述正方的核心观点和论证框架。",
    "con_opening": "你是反方一辩，现在进行开篇立论。请阐述反方的核心观点，并回应正方一辩的立论。",
    "pro_rebuttal": "你是正方二辩，现在进行驳论。针对反方一辩的立论进行反驳。",
    "con_rebuttal": "你是反方二辩，现在进行驳论。针对正方二辩的驳论进行再反驳。",
    "pro_cross_examine": "你是正方三辩，现在对反方一辩或二辩进行质询。请设计精准的问题，通过追问暴露对方论证中的逻辑漏洞。质询最多4轮，达成目的后请说“感谢，质询到此结束”来结束质询。",
    "con_cross_examine": "你是反方三辩，现在对正方一辩或二辩进行质询。请设计精准的问题，通过追问暴露对方论证中的逻辑漏洞。质询最多4轮，达成目的后请说“感谢，质询到此结束”来结束质询。",
    "pro_cross_summary": "你是正方三辩，现在进行质询小结。请总结质询中暴露的对方论证问题，将质询成果转化为正方论证的支撑。",
    "con_cross_summary": "你是反方三辩，现在进行质询小结。请总结质询中暴露的对方论证问题，将质询成果转化为反方论证的支撑。",
    "free_debate": "现在是自由辩论环节。你可以自由发言，反驳对方观点或强化本方论证。",
    "pro_closing": "你是正方四辩，现在进行总结陈词。请回顾整场辩论，总结正方核心立场，做最终的、有说服力的陈述。",
    "con_closing": "你是反方四辩，现在进行总结陈词。请回顾整场辩论，总结反方核心立场，做最终的、有说服力的陈述。",
    "verdict": "你是裁判，请基于整场辩论的表现，按照评分维度进行综合评分和裁决。输出JSON格式的裁决结果。",
}


# ---------------------------------------------------------------------------
# Agent factories
# ---------------------------------------------------------------------------


def create_agent(
    debate_id: str,
    debater_key: str,
    role_info: dict,
    topic: str,
    skill_name: str | None,
    llm: LLM,
) -> Agent:
    """Create a crewAI Agent with step_callback and optional skill.

    Args:
        debate_id: UUID of the debate.
        debater_key: e.g., "pro_1", "con_2", "judge".
        role_info: dict with "role", "goal", "backstory".
        topic: the debate topic.
        skill_name: optional huashu-nuwa skill name.
        llm: the LLM instance.
    """
    backstory = build_backstory_with_skill(role_info["backstory"], skill_name)

    agent = Agent(
        role=role_info["role"],
        goal=role_info["goal"],
        backstory=backstory,
        llm=llm,
        step_callback=_make_step_callback(debate_id, debater_key),
        verbose=False,
    )
    return agent


def create_pro_agent(
    debate_id: str,
    position: int,
    topic: str,
    skill_name: str | None = None,
) -> Agent:
    """Create a pro-side debater agent with streaming LLM."""
    debater_key = f"pro_{position}"
    llm = _make_llm(debate_id=debate_id, debater_key=debater_key)
    return create_agent(debate_id, debater_key, PRO_ROLES[position], topic, skill_name, llm)


def create_con_agent(
    debate_id: str,
    position: int,
    topic: str,
    skill_name: str | None = None,
) -> Agent:
    """Create a con-side debater agent with streaming LLM."""
    debater_key = f"con_{position}"
    llm = _make_llm(debate_id=debate_id, debater_key=debater_key)
    return create_agent(debate_id, debater_key, CON_ROLES[position], topic, skill_name, llm)


def create_judge_agent(
    debate_id: str,
    topic: str,
    skill_name: str | None = None,
) -> Agent:
    """Create the judge agent (no streaming — verdict handled separately)."""
    llm = _make_llm()
    return create_agent(debate_id, "judge", JUDGE_ROLE, topic, skill_name, llm)
