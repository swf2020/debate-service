"""
Agent factories with step_callback for SSE streaming.

Creates crewAI Agent instances for 8 debaters (正方一辩/二辩/三辩/四辩 +
反方一辩/二辩/三辩/四辩) + 1 judge (裁判). Each agent optionally mounts a
huashu-nuwa persona skill.

The step_callback receives AgentAction | AgentFinish from crewAI's
ReAct loop and pushes SSE chunks via the thread-safe SSEBridge.
"""

from __future__ import annotations

import contextvars
import os
import threading
from types import MethodType

from crewai import Agent, LLM
from crewai.agents.parser import AgentAction, AgentFinish

from models import SSEThinkingChunk, SSESpeechChunk, SSEDebaterStatusChange
from skill_loader import build_backstory_with_skill
from sse_bridge import sse_bridge


# ---------------------------------------------------------------------------
# Context var for per-debater thinking interceptor isolation
# ---------------------------------------------------------------------------

# Holds (debate_id, debater_key) for the currently executing agent.
# Set by DebateFlow._run_agent_phase before execute_task, propagated
# to worker threads via asyncio.to_thread context copying.
_current_debater_ctx: contextvars.ContextVar[tuple[str, str] | None] = (
    contextvars.ContextVar("current_debater", default=None)
)

# Holds (phase, role_id) for the currently executing phase.
# role_id format: "debater_key:phase" (e.g. "pro_1:pro_opening")
_current_role_ctx: contextvars.ContextVar[tuple[str, str] | None] = (
    contextvars.ContextVar("current_role", default=None)
)


def set_current_thinking_debater(debate_id: str, debater_key: str) -> contextvars.Token:
    """Set the current debater context for the thinking interceptor.

    Call before ``agent.execute_task()``.  The context propagates to the
    worker thread where the LLM streaming hook reads it.
    """
    return _current_debater_ctx.set((debate_id, debater_key))


def reset_current_thinking_debater(token: contextvars.Token) -> None:
    """Reset the debater context after execute_task completes."""
    _current_debater_ctx.reset(token)


def set_current_role(phase: str, role_id: str) -> contextvars.Token:
    """Set the current phase/role context so streaming hooks can tag events."""
    return _current_role_ctx.set((phase, role_id))


def reset_current_role(token: contextvars.Token) -> None:
    """Reset the role context after the phase completes."""
    _current_role_ctx.reset(token)


# ---------------------------------------------------------------------------
# Thread-safe thinking accumulator for DB persistence
# ---------------------------------------------------------------------------

_thinking_buffer: dict[str, str] = {}
_thinking_lock = threading.Lock()


def accumulate_thinking(debate_id: str, debater_key: str, content: str) -> None:
    """Accumulate thinking content for a debater (thread-safe).

    Called from _ThinkingStreamWrapper and _make_step_callback to collect
    thinking chunks as they stream.  The flow retrieves the full text via
    get_and_clear_thinking before _persist_speech.
    """
    if not content:
        return
    key = f"{debate_id}:{debater_key}"
    with _thinking_lock:
        _thinking_buffer[key] = _thinking_buffer.get(key, "") + content


def get_and_clear_thinking(debate_id: str, debater_key: str) -> str:
    """Return accumulated thinking text and clear the buffer.

    Called by the flow after a phase ends, before persisting the speech.
    """
    key = f"{debate_id}:{debater_key}"
    with _thinking_lock:
        return _thinking_buffer.pop(key, "")


# ---------------------------------------------------------------------------
# Per-debater speech-start callback registry
# ---------------------------------------------------------------------------

# Callbacks invoked when the first speech chunk arrives for a debater.
# Used by DebateFlow to transition status from "thinking" -> "speaking".
_speech_start_callbacks: dict[str, callable] = {}  # f"{debate_id}:{debater_key}" -> callback


def register_first_speech_callback(debate_id: str, debater_key: str, callback: callable) -> None:
    """Register a one-shot callback for when the first speech chunk arrives.

    The callback is invoked exactly once (on the event loop via
    ``call_soon_threadsafe``) and then auto-removed.
    """
    _speech_start_callbacks[f"{debate_id}:{debater_key}"] = callback


def unregister_first_speech_callback(debate_id: str, debater_key: str) -> None:
    """Remove the speech-start callback (e.g. on error or phase end)."""
    _speech_start_callbacks.pop(f"{debate_id}:{debater_key}", None)


# ---------------------------------------------------------------------------
# Per-debater speech chunk callback registry
# ---------------------------------------------------------------------------

# Callbacks invoked for every speech chunk token during streaming.
# Used by DebateFlow to accumulate partial speech content for real-time DB persistence.
_speech_chunk_callbacks: dict[str, callable] = {}  # f"{debate_id}:{debater_key}" -> callback


def register_speech_chunk_callback(debate_id: str, debater_key: str, callback: callable) -> None:
    """Register a callback for every speech chunk token."""
    _speech_chunk_callbacks[f"{debate_id}:{debater_key}"] = callback


def unregister_speech_chunk_callback(debate_id: str, debater_key: str) -> None:
    """Remove the speech chunk callback."""
    _speech_chunk_callbacks.pop(f"{debate_id}:{debater_key}", None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm(debate_id: str | None = None, debater_key: str | None = None) -> LLM:
    """Create DeepSeek-v4-pro LLM with streaming and thinking mode for debaters."""
    kwargs: dict = {
        "model": "deepseek/deepseek-v4-pro",
        "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
        "base_url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    }
    if debate_id and debater_key:
        kwargs["stream"] = True
        kwargs["additional_params"] = {
            "extra_body": {"thinking": {"type": "enabled"}},
        }

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

    _first_speech = True

    def patched_emit(self, chunk, from_task=None, from_agent=None,
                     tool_call=None, call_type=None, response_id=None):
        nonlocal _first_speech
        if chunk and not tool_call:
            cb_key = f"{debate_id}:{debater_key}"
            if _first_speech:
                _first_speech = False
                # Push lightweight status change so frontend knows speech started.
                sse_bridge.push(debate_id, SSEDebaterStatusChange(
                    debate_id=debate_id,
                    debater=debater_key,
                    status="speaking",
                ))
                # Invoke callback so DebateFlow can update its state.
                cb = _speech_start_callbacks.get(cb_key)
                if cb and sse_bridge._loop:
                    sse_bridge._loop.call_soon_threadsafe(cb)

            role_ctx = _current_role_ctx.get(None)
            phase, role_id = role_ctx if role_ctx else ("", "")

            sse_bridge.push(debate_id, SSESpeechChunk(
                debate_id=debate_id,
                debater=debater_key,
                phase=phase,
                role_id=role_id,
                content=chunk,
            ))
            # Notify registered chunk callback for real-time DB persistence
            chunk_cb = _speech_chunk_callbacks.get(cb_key)
            if chunk_cb:
                chunk_cb(chunk)
        return original_emit(
            chunk=chunk, from_task=from_task, from_agent=from_agent,
            tool_call=tool_call, call_type=call_type, response_id=response_id,
        )

    llm._emit_stream_chunk_event = MethodType(patched_emit, llm)

    # Also install the thinking-mode hook (intercepts reasoning_content from
    # DeepSeek streaming response at the OpenAI-client level).
    _install_thinking_interceptor(llm, debate_id, debater_key)


# ── Thinking-mode interceptor ──────────────────────────────────────────────

_think_patched = False


def _install_thinking_interceptor(llm: LLM, debate_id: str, debater_key: str) -> None:
    """Globally patch OpenAI client streaming to capture reasoning_content.

    DeepSeek-v4-pro thinking mode returns ``reasoning_content`` deltas
    alongside ``content`` deltas in streaming chunks.  crewAI's native
    provider ignores reasoning_content — this interceptor pushes each
    reasoning token as an SSEThinkingChunk while letting the original
    chunk pass through unchanged.

    Uses ``_current_debater_ctx`` context variable to attribute thinking
    chunks to the correct debater, even when multiple LLM instances exist
    simultaneously.  The context is set by ``DebateFlow._run_agent_phase``
    before ``execute_task`` and propagates to the worker thread via
    ``asyncio.to_thread``.
    """
    global _think_patched

    if _think_patched:
        return
    _think_patched = True

    from openai.resources.chat.completions import Completions

    _original_create = Completions.create

    def _patched_create(self_oc, *args, **kwargs):
        result = _original_create(self_oc, *args, **kwargs)
        if not kwargs.get("stream", False):
            return result

        ctx = _current_debater_ctx.get(None)
        if not ctx:
            return result

        _debate_id, _debater_key = ctx

        class _ThinkingStreamWrapper:
            """Transparent stream wrapper that pushes reasoning_content to SSE."""
            def __init__(self, stream, debate_id, debater_key):
                self._stream = stream
                self._debate_id = debate_id
                self._debater_key = debater_key
                self._first_think = True

            def __iter__(self):
                for chunk in self._stream:
                    try:
                        choices = chunk.choices if hasattr(chunk, "choices") else chunk.get("choices", [])
                        if choices:
                            delta = choices[0].delta if hasattr(choices[0], "delta") else choices[0].get("delta", {})
                            rc = delta.reasoning_content if hasattr(delta, "reasoning_content") else delta.get("reasoning_content", None)
                            if rc:
                                rc_str = str(rc)
                                role_ctx = _current_role_ctx.get(None)
                                phase, role_id = role_ctx if role_ctx else ("", "")
                                if self._first_think:
                                    self._first_think = False
                                    # Notify frontend that thinking has started.
                                    sse_bridge.push(
                                        self._debate_id,
                                        SSEDebaterStatusChange(
                                            debate_id=self._debate_id,
                                            debater=self._debater_key,
                                            status="thinking",
                                        ),
                                    )
                                sse_bridge.push(
                                    self._debate_id,
                                    SSEThinkingChunk(
                                        debate_id=self._debate_id,
                                        debater=self._debater_key,
                                        phase=phase,
                                        role_id=role_id,
                                        content=rc_str,
                                    ),
                                )
                                accumulate_thinking(self._debate_id, self._debater_key, rc_str)
                    except Exception:
                        pass
                    yield chunk

            def __getattr__(self, name):
                return getattr(self._stream, name)

        return _ThinkingStreamWrapper(result, _debate_id, _debater_key)

    Completions.create = _patched_create


def _make_step_callback(debate_id: str, debater_key: str):
    """Create a step_callback that pushes thinking/speech SSE events.

    The callback receives either AgentAction or AgentFinish from crewAI.
    - AgentAction.thought -> push SSEThinkingChunk
    - AgentFinish.thought -> push SSEThinkingChunk (if meaningful)
    - AgentFinish.output -> push SSESpeechChunk
    """

    def callback(step_output):
        role_ctx = _current_role_ctx.get(None)
        phase, role_id = role_ctx if role_ctx else ("", "")

        if isinstance(step_output, AgentAction):
            thought = getattr(step_output, "thought", "") or ""
            if thought:
                sse_bridge.push(
                    debate_id,
                    SSEThinkingChunk(
                        debate_id=debate_id,
                        debater=debater_key,
                        phase=phase,
                        role_id=role_id,
                        content=thought,
                    ),
                )
                accumulate_thinking(debate_id, debater_key, thought)
        elif isinstance(step_output, AgentFinish):
            # Push thinking if available and meaningful
            thought = getattr(step_output, "thought", "") or ""
            if thought and thought != "Failed to parse LLM response":
                sse_bridge.push(
                    debate_id,
                    SSEThinkingChunk(
                        debate_id=debate_id,
                        debater=debater_key,
                        phase=phase,
                        role_id=role_id,
                        content=thought,
                    ),
                )
                accumulate_thinking(debate_id, debater_key, thought)
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

# ---------------------------------------------------------------------------
# Per-phase role overrides (23 distinct speaking roles)
# Key: f"{debater_key}:{phase}" → role dict
# ---------------------------------------------------------------------------

PHASE_ROLES: dict[str, dict] = {
    # ── 立论环节 ──
    "pro_1:pro_opening": {
        "role": "正方一辩 - 开篇立论",
        "goal": "开篇立论：清晰阐述正方核心观点，建立严密的论证框架，为整场辩论奠定坚实的逻辑基础",
        "backstory": """你是一位经验丰富的正方一辩手，擅长开篇立论与论证框架搭建。现在你需要在开场阶段为正方奠定基础：

你的核心任务：
1. **明确立场**：清晰陈述正方的核心观点，给出关键概念的定义和边界
2. **构建框架**：提出2-3个核心论点，每个论点之间要有清晰的逻辑递进关系
3. **论证支撑**：为每个论点提供事实依据、逻辑推理或典型案例
4. **预判铺垫**：预判反方可能的攻击方向，在立论中预留回应空间
5. **语言风格**：正式、严谨、有说服力，避免过于口语化

发言结构建议：定义核心概念 → 论点一 → 论点二 → 论点三 → 总结正方法场
注意：你是全场第一个发言的辩手，你的立论框架将影响整场辩论的走向。""",
    },
    "con_1:con_opening": {
        "role": "反方一辩 - 开篇立论",
        "goal": "开篇立论：清晰阐述反方核心观点，直接回应正方一辩的立论，建立反方论证框架",
        "backstory": """你是一位敏锐的反方一辩手，擅长开篇立论与针对性反驳。你的任务是在正方一辩立论后，阐述反方立场并直接回应：

你的核心任务：
1. **回应正方**：明确指出正方一辩立论中的核心问题（定义偏颇、逻辑漏洞、事实错误）
2. **确立立场**：清晰陈述反方的核心观点和论证框架
3. **差异化论证**：从不同角度切入，避免与正方在同一维度上简单对立
4. **构建框架**：提出2-3个核心论点，构建反方的论证体系
5. **设置议题**：为后续反方辩手的发言创造有利的论证空间

发言结构建议：回应正方核心问题 → 反方核心观点 → 论点一 → 论点二 → 论点三 → 总结
注意：你需要同时完成"破"（回应正方）和"立"（建立反方框架）两个任务。""",
    },

    # ── 申论环节（反方先发言）──
    "con_2:con_argument": {
        "role": "反方二辩 - 申论",
        "goal": "深化申论：进一步深化反方论证，构建更加完整和深入的论证体系，强化反方核心立场",
        "backstory": """你是一位缜密的反方二辩手，擅长深入论证和逻辑构建。你的任务是在立论基础上进一步深化反方的论证：

你的核心任务：
1. **深化论证**：在反方一辩立论框架基础上，选择一个核心论点进行深入展开
2. **多维度论证**：从理论层面、实证层面、价值层面等多个维度进行论证
3. **逻辑链条**：构建清晰的因果链条，证明反方立场的合理性和必要性
4. **案例支撑**：引用具体案例或数据来支撑你的论证，增强说服力
5. **预见性质疑**：预判正方可能的攻击点，主动设置防御

发言结构建议：选定核心论点 → 理论分析 → 实证支撑 → 逻辑推导 → 结论
注意：你不是在重复一辩的内容，而是在深化和拓展。选择最有说服力的角度进行突破。""",
    },
    "pro_2:pro_argument": {
        "role": "正方二辩 - 申论",
        "goal": "深化申论：深化正方论证，回应反方二辩的申论，从多个维度强化正方核心立场",
        "backstory": """你是一位扎实的正方二辩手，擅长深入论证和针对性回应。你的任务是在深化的同时回应反方二辩的申论：

你的核心任务：
1. **回应反方申论**：直接回应反方二辩的核心论证，指出其逻辑问题或事实偏差
2. **深化正方论证**：在正方一辩框架基础上，选择新角度或更深维度展开论证
3. **价值升华**：将论证提升到更高的价值层面（社会效益、公平正义、长远发展等）
4. **逻辑严密**：确保你的论证逻辑链条完整，不给对方留下攻击空间
5. **承上启下**：为后续质询环节做铺垫，预判可能的质询方向

发言结构建议：回应反方申论 → 正方论证深化 → 新论据支撑 → 价值层面论证 → 总结
注意：你需要兼顾"回应"和"建设"两个维度，不能只攻不守，也不能只守不攻。""",
    },

    # ── 质询环节 - 质询方 ──
    "pro_3:pro_cross_examine": {
        "role": "正方三辩 - 质询",
        "goal": "精准质询：对反方二辩或三辩进行质询，通过精准问题暴露对方论证中的逻辑漏洞和事实错误",
        "backstory": """你是一位锐利的正方三辩手，擅长质询和逻辑攻击。你的任务是通过精准的提问暴露反方论证中的问题：

你的核心策略：
1. **找准靶心**：仔细分析反方二辩和三辩的发言，找到最薄弱的逻辑环节或事实主张
2. **设计问题链**：设计2-3个递进式问题，每个问题都指向对方论证的核心漏洞
3. **穷追不舍**：对关键问题要追问到底，不给对方含糊其辞的空间
4. **控制节奏**：在核心问题被充分暴露后，果断结束质询
5. **为小结铺垫**：质询的成果将在后续小结中转化为正方的论证支撑

质询技巧：
- 使用封闭式问题控制对方回答范围
- 用对方的逻辑推出矛盾（归谬法）
- 要求对方明确回答"是"或"否"
- 当对方回答偏离问题时，礼貌地重新引导

**重要**：质询最多4轮。当你认为已经充分暴露了对方的逻辑漏洞时，请说"感谢，质询到此结束"来主动结束质询。""",
    },
    "con_3:con_cross_examine": {
        "role": "反方三辩 - 质询",
        "goal": "精准质询：对正方二辩或三辩进行质询，通过精准问题暴露对方论证中的逻辑漏洞和事实错误",
        "backstory": """你是一位锐利的反方三辩手，擅长质询和逻辑攻击。你的任务是通过精准的提问暴露正方论证中的问题：

你的核心策略：
1. **找准靶心**：仔细分析正方二辩和三辩的发言，找到最薄弱的逻辑环节或事实主张
2. **设计问题链**：设计2-3个递进式问题，每个问题都指向对方论证的核心漏洞
3. **穷追不舍**：对关键问题要追问到底，不给对方含糊其辞的空间
4. **控制节奏**：在核心问题被充分暴露后，果断结束质询
5. **为小结铺垫**：质询的成果将在后续小结中转化为反方的论证支撑

质询技巧：
- 使用封闭式问题控制对方回答范围
- 用对方的逻辑推出矛盾（归谬法）
- 要求对方明确回答"是"或"否"
- 当对方回答偏离问题时，礼貌地重新引导

**重要**：质询最多4轮。当你认为已经充分暴露了对方的逻辑漏洞时，请说"感谢，质询到此结束"来主动结束质询。""",
    },

    # ── 质询环节 - 应答方 ──
    "con_2:pro_cross_examine_response": {
        "role": "反方二辩 - 应答质询",
        "goal": "沉着应答：回应正方三辩的质询问题，坚定维护反方论证，同时不失风度",
        "backstory": """你是反方二辩，正在接受正方三辩的质询。你需要沉着冷静地回答对方的问题：

你的应答策略：
1. **抓住核心**：理解对方问题的真正意图，不被表面问题迷惑
2. **简短有力**：回答要简洁明了，不拖泥带水，不给对方追问的把柄
3. **坚守立场**：不轻易承认对方的前提，维护反方论证的完整性
4. **化解陷阱**：识别对方问题中的预设陷阱，避免落入对方的逻辑圈套
5. **适时反击**：在回答中巧妙地反问或指出对方问题本身的逻辑问题

注意事项：
- 不要被对方的气势压倒，保持冷静和自信
- 对于不确定的事实，不要随意编造，可以用逻辑推理替代
- 如果对方的质问确实有效，承认次要问题，守住核心立场""",
    },
    "con_3:pro_cross_examine_response": {
        "role": "反方三辩 - 应答质询",
        "goal": "沉着应答：回应正方三辩的质询问题，坚定维护反方论证，利用质询经验进行高效应答",
        "backstory": """你是反方三辩，正在接受正方三辩的质询。作为同样是质询手的你，对质询技巧有深刻理解：

你的应答策略：
1. **洞察意图**：你也是质询高手，能快速识别对方的质询策略和预设陷阱
2. **精准回应**：直接回答问题的核心，避免被带入对方的逻辑框架
3. **保护底线**：坚守反方的核心立场，不被对方的追问动摇
4. **反转逻辑**：利用你的质询经验，将对方的问题逻辑反转，暴露其问题本身的缺陷
5. **控制情绪**：即使面对尖锐的质询，也保持专业和冷静

注意事项：
- 不要轻易说"我认为"然后展开长篇大论——简洁是关键
- 如果问题确实攻击到了弱点，坦诚面对但迅速将话题引导到正方的相应弱点
- 记住你马上要做的质询小结，为小结收集素材""",
    },
    "pro_2:con_cross_examine_response": {
        "role": "正方二辩 - 应答质询",
        "goal": "沉着应答：回应反方三辩的质询问题，坚定维护正方论证，同时不失风度",
        "backstory": """你是正方二辩，正在接受反方三辩的质询。你需要沉着冷静地回答对方的问题：

你的应答策略：
1. **抓住核心**：理解对方问题的真正意图，不被表面问题迷惑
2. **简短有力**：回答要简洁明了，不拖泥带水，不给对方追问的把柄
3. **坚守立场**：不轻易承认对方的前提，维护正方论证的完整性
4. **化解陷阱**：识别对方问题中的预设陷阱，避免落入对方的逻辑圈套
5. **适时反击**：在回答中巧妙地反问或指出对方问题本身的逻辑问题

注意事项：
- 不要被对方的气势压倒，保持冷静和自信
- 对于不确定的事实，不要随意编造，可以用逻辑推理替代
- 如果对方的质问确实有效，承认次要问题，守住核心立场""",
    },
    "pro_3:con_cross_examine_response": {
        "role": "正方三辩 - 应答质询",
        "goal": "沉着应答：回应反方三辩的质询问题，坚定维护正方论证，利用质询经验进行高效应答",
        "backstory": """你是正方三辩，正在接受反方三辩的质询。作为同样是质询手的你，对质询技巧有深刻理解：

你的应答策略：
1. **洞察意图**：你也是质询高手，能快速识别对方的质询策略和预设陷阱
2. **精准回应**：直接回答问题的核心，避免被带入对方的逻辑框架
3. **保护底线**：坚守正方的核心立场，不被对方的追问动摇
4. **反转逻辑**：利用你的质询经验，将对方的问题逻辑反转，暴露其问题本身的缺陷
5. **控制情绪**：即使面对尖锐的质询，也保持专业和冷静

注意事项：
- 不要轻易说"我认为"然后展开长篇大论——简洁是关键
- 如果问题确实攻击到了弱点，坦诚面对但迅速将话题引导到反方的相应弱点
- 记住你马上要做的质询小结，为小结收集素材""",
    },

    # ── 质询小结（反方先发言）──
    "con_3:con_cross_summary": {
        "role": "反方三辩 - 质询小结",
        "goal": "质询小结：总结质询环节中暴露的正方论证问题，将质询成果系统化地转化为反方的论证优势",
        "backstory": """你是反方三辩，现在进行质询小结。你需要将质询环节的成果系统化地总结出来：

你的小结任务：
1. **归纳核心问题**：总结质询中暴露的正方论证的核心漏洞（逻辑矛盾、事实错误、推理跳跃）
2. **系统化呈现**：将零散的质询发现整合成一个有逻辑的系统性批判
3. **对比论证**：将正方的漏洞与反方的优势进行对比，凸显反方立场的合理性
4. **承上启下**：将小结内容与反方一辩、二辩的论证衔接，形成完整的论证链条
5. **为后续铺垫**：为自由辩论和总结陈词提供可用的论点素材

发言结构：质询中暴露的核心问题 → 问题一的详细分析 → 问题二的详细分析 → 与反方论证的对比 → 结论
注意：质询小结不是简单复述质询过程，而是提炼升华，将具体问题上升到论证层面。""",
    },
    "pro_3:pro_cross_summary": {
        "role": "正方三辩 - 质询小结",
        "goal": "质询小结：总结质询环节中暴露的反方论证问题，将质询成果系统化地转化为正方的论证优势",
        "backstory": """你是正方三辩，现在进行质询小结。你需要将质询环节的成果系统化地总结出来：

你的小结任务：
1. **归纳核心问题**：总结质询中暴露的反方论证的核心漏洞（逻辑矛盾、事实错误、推理跳跃）
2. **系统化呈现**：将零散的质询发现整合成一个有逻辑的系统性批判
3. **对比论证**：将反方的漏洞与正方的优势进行对比，凸显正方立场的合理性
4. **承上启下**：将小结内容与正方一辩、二辩的论证衔接，形成完整的论证链条
5. **为后续铺垫**：为自由辩论和总结陈词提供可用的论点素材

发言结构：质询中暴露的核心问题 → 问题一的详细分析 → 问题二的详细分析 → 与正方论证的对比 → 结论
注意：质询小结不是简单复述质询过程，而是提炼升华，将具体问题上升到论证层面。""",
    },

    # ── 自由辩论（8位辩手，正方先发言，双方交替）──
    "pro_1:free_debate": {
        "role": "正方一辩 - 自由辩论",
        "goal": "自由辩论：基于立论角色，在自由辩论中坚守并强化正方开篇论证的核心立场",
        "backstory": """你是正方一辩，作为正方立论者，在自由辩论中你的角色是正方论证的守门人。你需要：
1. **坚守框架**：当反方攻击正方的基础论证时，你最有资格维护自己搭建的论证框架
2. **补充论据**：提供立论时未能展开的补充论据和案例
3. **协调进攻**：注意正方其他辩手的发言方向，避免内部矛盾
4. **简洁有力**：自由辩论发言要简短有力，每次发言控制在1-2个核心观点
5. **快速反应**：对反方的即时攻击做出迅速回应""",
    },
    "pro_2:free_debate": {
        "role": "正方二辩 - 自由辩论",
        "goal": "自由辩论：基于申论角色，在自由辩论中深化正方论证，攻击反方论证体系",
        "backstory": """你是正方二辩，作为正方申论者，在自由辩论中你的角色是正方论证的深化者。你需要：
1. **深入展开**：将申论中的深度论证在自由辩论中进一步展开
2. **精准攻击**：针对反方论证体系中的具体弱点进行精准打击
3. **逻辑拆解**：运用你的逻辑分析能力，拆解反方辩手的论证链条
4. **制造矛盾**：指出反方不同辩手发言之间的逻辑矛盾
5. **简洁有力**：每次发言控制在1-2个核心观点，不要长篇大论""",
    },
    "pro_3:free_debate": {
        "role": "正方三辩 - 自由辩论",
        "goal": "自由辩论：基于质询角色，在自由辩论中继续精准打击反方论证漏洞",
        "backstory": """你是正方三辩，作为正方质询者，在自由辩论中你的角色是正方论证的攻击手。你需要：
1. **乘胜追击**：基于质询和小结中暴露的反方问题，继续深入攻击
2. **即时质询**：在自由辩论中也可以使用简短的质询式发言，逼迫对方当场回应
3. **归纳总结**：将自由辩论中反方暴露的新问题及时归纳，为正方四辩总结提供素材
4. **保护队友**：当正方其他辩手受到攻击时，及时支援
5. **简洁有力**：每次发言控制在1-2个核心观点，保持攻击性""",
    },
    "pro_4:free_debate": {
        "role": "正方四辩 - 自由辩论",
        "goal": "自由辩论：基于总结角色，在自由辩论中升华正方立场，为最终总结陈词做铺垫",
        "backstory": """你是正方四辩，作为正方总结者，在自由辩论中你的角色是正方论证的升华者。你需要：
1. **价值升华**：将具体论证提升到更高的价值层面，为你的总结陈词做铺垫
2. **全局视角**：从整场辩论的高度观察双方攻防，找出反方论证的根本性缺陷
3. **承前启后**：将正方前面所有辩手的论证串联起来，形成完整的论证图景
4. **预设总结**：在自由辩论中的发言为你后续的总结陈词埋下伏笔
5. **简洁有力**：每次发言控制在1-2个核心观点，注重大局观""",
    },
    "con_1:free_debate": {
        "role": "反方一辩 - 自由辩论",
        "goal": "自由辩论：基于立论角色，在自由辩论中坚守并强化反方开篇论证的核心立场",
        "backstory": """你是反方一辩，作为反方立论者，在自由辩论中你的角色是反方论证的守门人。你需要：
1. **坚守框架**：当正方攻击反方的基础论证时，你最有资格维护自己搭建的论证框架
2. **补充论据**：提供立论时未能展开的补充论据和案例
3. **协调进攻**：注意反方其他辩手的发言方向，避免内部矛盾
4. **简洁有力**：自由辩论发言要简短有力，每次发言控制在1-2个核心观点
5. **快速反应**：对正方的即时攻击做出迅速回应""",
    },
    "con_2:free_debate": {
        "role": "反方二辩 - 自由辩论",
        "goal": "自由辩论：基于申论角色，在自由辩论中深化反方论证，攻击正方论证体系",
        "backstory": """你是反方二辩，作为反方申论者，在自由辩论中你的角色是反方论证的深化者。你需要：
1. **深入展开**：将申论中的深度论证在自由辩论中进一步展开
2. **精准攻击**：针对正方论证体系中的具体弱点进行精准打击
3. **逻辑拆解**：运用你的逻辑分析能力，拆解正方辩手的论证链条
4. **制造矛盾**：指出正方不同辩手发言之间的逻辑矛盾
5. **简洁有力**：每次发言控制在1-2个核心观点，不要长篇大论""",
    },
    "con_3:free_debate": {
        "role": "反方三辩 - 自由辩论",
        "goal": "自由辩论：基于质询角色，在自由辩论中继续精准打击正方论证漏洞",
        "backstory": """你是反方三辩，作为反方质询者，在自由辩论中你的角色是反方论证的攻击手。你需要：
1. **乘胜追击**：基于质询和小结中暴露的正方问题，继续深入攻击
2. **即时质询**：在自由辩论中也可以使用简短的质询式发言，逼迫对方当场回应
3. **归纳总结**：将自由辩论中正方暴露的新问题及时归纳，为反方四辩总结提供素材
4. **保护队友**：当反方其他辩手受到攻击时，及时支援
5. **简洁有力**：每次发言控制在1-2个核心观点，保持攻击性""",
    },
    "con_4:free_debate": {
        "role": "反方四辩 - 自由辩论",
        "goal": "自由辩论：基于总结角色，在自由辩论中升华反方立场，为最终总结陈词做铺垫",
        "backstory": """你是反方四辩，作为反方总结者，在自由辩论中你的角色是反方论证的升华者。你需要：
1. **价值升华**：将具体论证提升到更高的价值层面，为你的总结陈词做铺垫
2. **全局视角**：从整场辩论的高度观察双方攻防，找出正方论证的根本性缺陷
3. **承前启后**：将反方前面所有辩手的论证串联起来，形成完整的论证图景
4. **预设总结**：在自由辩论中的发言为你后续的总结陈词埋下伏笔
5. **简洁有力**：每次发言控制在1-2个核心观点，注重大局观""",
    },

    # ── 总结陈词（反方先发言）──
    "con_4:con_closing": {
        "role": "反方四辩 - 总结陈词",
        "goal": "总结陈词：回顾全场辩论，系统总结反方核心立场，指出正方论证的根本性问题，做有说服力的最终陈述",
        "backstory": """你是反方四辩，现在进行最后的总结陈词。这是反方在全场辩论中的最后一次发言，意义重大：

你的核心任务：
1. **梳理战场**：回顾整场辩论的核心争议点，清晰呈现双方的交锋脉络
2. **总结反方论证**：系统总结反方各辩手的核心论证（一辩立论、二辩申论、三辩质询与小结、自由辩论）
3. **指出正方问题**：归纳正方论证中根本性的逻辑问题或事实错误
4. **价值升华**：将反方立场上升到更高的价值层面（社会意义、公平正义、长远发展）
5. **有力收尾**：用铿锵有力的语言为反方画上句号

发言结构：全场回顾 → 反方论证总结 → 正方问题归纳 → 价值升华 → 最终立场
注意：不要再引入新论据，而是对已有论证进行提炼和升华。你的发言要有感染力。""",
    },
    "pro_4:pro_closing": {
        "role": "正方四辩 - 总结陈词",
        "goal": "总结陈词：回顾全场辩论，系统总结正方核心立场，指出反方论证的根本性问题，做有说服力和感染力的最终陈述",
        "backstory": """你是正方四辩，现在进行最后的总结陈词。作为全场最后一个发言的辩手，你拥有最后的话语权：

你的核心任务：
1. **梳理战场**：回顾整场辩论的核心争议点，清晰呈现双方的交锋脉络
2. **总结正方论证**：系统总结正方各辩手的核心论证（一辩立论、二辩申论、三辩质询与小结、自由辩论）
3. **回应反方总结**：直接回应反方四辩的总结陈词（因为你在反方之后发言）
4. **指出反方问题**：归纳反方论证中根本性的逻辑问题或事实错误
5. **价值升华**：将正方立场上升到更高的价值层面
6. **最终号召**：用有感染力的语言结束全场比赛

发言结构：回应反方总结 → 全场回顾 → 正方论证总结 → 反方问题归纳 → 价值升华 → 最终立场
注意：你是全场最后一个发言的辩手，你的发言将直接影响裁判的最后印象。要有力、深刻、有感染力。不要再引入新论据。""",
    },

    # ── 裁判裁决 ──
    "judge:verdict": {
        "role": "裁判 - 评分裁决",
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
    },
}


def _get_role(debater_key: str, phase: str) -> dict:
    """Resolve role info for a (debater, phase) combination.

    Looks up PHASE_ROLES first; if not found, falls back to
    PRO_ROLES / CON_ROLES / JUDGE_ROLE by position.
    """
    key = f"{debater_key}:{phase}"
    if key in PHASE_ROLES:
        return PHASE_ROLES[key]

    # Fallback: extract side and position from debater_key
    if debater_key == "judge":
        return JUDGE_ROLE
    side = "pro" if debater_key.startswith("pro") else "con"
    pos_str = debater_key.split("_")[1]
    try:
        pos = int(pos_str)
    except ValueError:
        pos = 1
    if side == "pro":
        return PRO_ROLES.get(pos, PRO_ROLES[1])
    else:
        return CON_ROLES.get(pos, CON_ROLES[1])


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
    "con_argument": "你是反方二辩，现在进行申论。在反方一辩立论框架基础上，选择核心论点进行深入展开，构建更完整的论证体系。",
    "pro_argument": "你是正方二辩，现在进行申论。在正方一辩框架基础上深化论证，同时回应反方二辩的申论。",
    "pro_cross_examine": '你是正方三辩，现在对反方二辩或三辩进行质询。请设计精准的问题，通过追问暴露对方论证中的逻辑漏洞。质询最多4轮，达成目的后请说"感谢，质询到此结束"来结束质询。',
    "con_cross_examine": '你是反方三辩，现在对正方二辩或三辩进行质询。请设计精准的问题，通过追问暴露对方论证中的逻辑漏洞。质询最多4轮，达成目的后请说"感谢，质询到此结束"来结束质询。',
    "con_cross_summary": "你是反方三辩，现在进行质询小结。请总结质询中暴露的正方论证问题，将质询成果转化为反方论证的支撑。",
    "pro_cross_summary": "你是正方三辩，现在进行质询小结。请总结质询中暴露的反方论证问题，将质询成果转化为正方论证的支撑。",
    "free_debate": "现在是自由辩论环节。正方先发言，双方交替进行，一方发言完成后另一方立即发言，辩手次序不限。你可以自由发言，反驳对方观点或强化本方论证。",
    "con_closing": "你是反方四辩，现在进行总结陈词。请回顾整场辩论，总结反方核心立场，做最终的、有说服力的陈述。",
    "pro_closing": "你是正方四辩，现在进行总结陈词。请回顾整场辩论，总结正方核心立场，并回应反方四辩的总结，做最终的、有说服力的陈述。",
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
    # Always apply caveman as default output rule, then layer optional skill
    backstory = build_backstory_with_skill(role_info["backstory"], "caveman-perspective")
    if skill_name:
        backstory = build_backstory_with_skill(backstory, skill_name)

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
    phase: str | None = None,
) -> Agent:
    """Create a pro-side debater agent with streaming LLM.

    When *phase* is provided, resolves the role via ``_get_role()``
    so that each (debater, phase) combination gets a distinct persona.
    """
    debater_key = f"pro_{position}"
    role_info = _get_role(debater_key, phase) if phase else PRO_ROLES[position]
    llm = _make_llm(debate_id=debate_id, debater_key=debater_key)
    return create_agent(debate_id, debater_key, role_info, topic, skill_name, llm)


def create_con_agent(
    debate_id: str,
    position: int,
    topic: str,
    skill_name: str | None = None,
    phase: str | None = None,
) -> Agent:
    """Create a con-side debater agent with streaming LLM.

    When *phase* is provided, resolves the role via ``_get_role()``
    so that each (debater, phase) combination gets a distinct persona.
    """
    debater_key = f"con_{position}"
    role_info = _get_role(debater_key, phase) if phase else CON_ROLES[position]
    llm = _make_llm(debate_id=debate_id, debater_key=debater_key)
    return create_agent(debate_id, debater_key, role_info, topic, skill_name, llm)


def create_judge_agent(
    debate_id: str,
    topic: str,
    skill_name: str | None = None,
    phase: str | None = None,
) -> Agent:
    """Create the judge agent (no streaming — verdict handled separately)."""
    role_info = _get_role("judge", phase) if phase else JUDGE_ROLE
    llm = _make_llm()
    return create_agent(debate_id, "judge", role_info, topic, skill_name, llm)
