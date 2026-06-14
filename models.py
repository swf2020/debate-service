"""
Debate service data models.

All Pydantic models used throughout the debate service are defined here.
Other modules (flow, routes, db) import from this file.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from crewai.flow.runtime import FlowState


# ── Core state ──────────────────────────────────────────────────────────


class DebateState(FlowState):
    """Persistent state for a single debate run.

    Used as ``self.state`` inside ``DebateFlow`` methods.
    """

    topic: str = ""
    total_rounds: int = 1
    current_round: int = 1
    current_phase: str = ""

    pro_skills: dict = Field(
        default_factory=lambda: {"debater_1": "munger-perspective",
                                 "debater_2": None,
                                 "debater_3": None}
    )
    con_skills: dict = Field(
        default_factory=lambda: {"debater_1": None,
                                 "debater_2": None,
                                 "debater_3": None}
    )
    judge_skill: str | None = None

    debate_history: list[dict] = Field(default_factory=list)
    paused: bool = False
    verdict: dict | None = None
    winner: str | None = None
    id: str = ""


# ── Request / response models ───────────────────────────────────────────


class SkillConfig(BaseModel):
    """Skills assigned to each debater slot for one side (pro or con)."""

    debater_1: str | None = None
    debater_2: str | None = None
    debater_3: str | None = None


class StartDebateRequest(BaseModel):
    """Payload to start a new debate."""

    topic: str
    rounds: int = Field(default=1, ge=1, le=3)
    pro_skills: SkillConfig = Field(default_factory=SkillConfig)
    con_skills: SkillConfig = Field(default_factory=SkillConfig)
    judge_skill: str | None = None


class StartDebateResponse(BaseModel):
    """Response returned immediately after starting a debate."""

    debate_id: str
    status: str = "running"


# ── History / summary models ────────────────────────────────────────────


class DebateSummary(BaseModel):
    """Full summary of a completed debate, used for history replay."""

    id: str
    topic: str
    total_rounds: int
    status: str
    pro_skills: dict
    con_skills: dict
    judge_skill: str | None = None
    winner: str | None = None
    verdict: dict | None = None
    created_at: str = ""
    finished_at: str | None = None
    speeches: list[dict] = Field(default_factory=list)


# ── SSE event models ────────────────────────────────────────────────────


class SSEPhaseStart(BaseModel):
    type: Literal["phase_start"] = "phase_start"
    debate_id: str
    phase: str
    debater: str
    round_num: int


class SSEThinkingChunk(BaseModel):
    type: Literal["thinking_chunk"] = "thinking_chunk"
    debate_id: str
    debater: str
    content: str


class SSESpeechChunk(BaseModel):
    type: Literal["speech_chunk"] = "speech_chunk"
    debate_id: str
    debater: str
    content: str


class SSEPhaseEnd(BaseModel):
    type: Literal["phase_end"] = "phase_end"
    debate_id: str
    phase: str
    debater: str


class SSEVerdictChunk(BaseModel):
    type: Literal["verdict_chunk"] = "verdict_chunk"
    debate_id: str
    content: str
    scores: dict | None = None


class SSEPaused(BaseModel):
    type: Literal["paused"] = "paused"
    debate_id: str


class SSEResumed(BaseModel):
    type: Literal["resumed"] = "resumed"
    debate_id: str


class SSEDebateEnd(BaseModel):
    type: Literal["debate_end"] = "debate_end"
    debate_id: str
    verdict: dict


class SSEHistoryReplay(BaseModel):
    """Sent on SSE reconnect to restore past speeches."""

    type: Literal["history_replay"] = "history_replay"
    debate_id: str
    topic: str
    total_rounds: int
    current_round: int
    current_phase: str
    paused: bool
    status: str
    pro_skills: dict = Field(default_factory=dict)
    con_skills: dict = Field(default_factory=dict)
    judge_skill: str | None = None
    speeches: list[dict] = Field(default_factory=list)


class SSEError(BaseModel):
    type: Literal["error"] = "error"
    debate_id: str
    message: str
