"""
Quick tests for debate-service/models.py.

Run::

    cd debate-service && source .venv/bin/activate && python test_models.py
"""

import json
import sys
import traceback

from models import (
    DebateState,
    SkillConfig,
    StartDebateRequest,
    StartDebateResponse,
    DebateSummary,
    SSEPhaseStart,
    SSEThinkingChunk,
    SSESpeechChunk,
    SSECrossQChunk,
    SSECrossAChunk,
    SSEPhaseEnd,
    SSEVerdictChunk,
    SSEPaused,
    SSEResumed,
    SSEStateSnapshot,
    SSEDebateEnd,
    SSEHistoryReplay,
    SSEError,
)

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {detail}")


def run_test(name: str, fn):
    print(f"\n=== {name} ===")
    try:
        fn()
    except Exception:
        global failed
        failed += 1
        traceback.print_exc()
        print(f"  FAIL  {name} (unhandled exception)")


# ---------------------------------------------------------------------------
# 1. DebateState defaults
# ---------------------------------------------------------------------------
def test_debate_state_defaults():
    s = DebateState()
    check("topic defaults to ''", s.topic == "")
    check("total_rounds defaults to 1", s.total_rounds == 1)
    check("current_round defaults to 1", s.current_round == 1)
    check("current_phase defaults to ''", s.current_phase == "")
    check("format defaults to cdwc", s.format == "cdwc")
    check("current_debater defaults to ''", s.current_debater == "")
    check("cross_examine_round defaults to 0", s.cross_examine_round == 0)
    check("debater_status has pro_1 key", "pro_1" in s.debater_status)
    check("debater_status has con_4 key", "con_4" in s.debater_status)
    check("debater_status pro_1 is waiting", s.debater_status["pro_1"] == "waiting")
    check("debater_status judge is waiting", s.debater_status["judge"] == "waiting")
    check("pro_skills has debater_1 key", "debater_1" in s.pro_skills)
    check("con_skills has debater_1 key", "debater_1" in s.con_skills)
    check("debate_history is empty list", s.debate_history == [])
    check("paused defaults to False", s.paused is False)
    check("verdict defaults to None", s.verdict is None)
    check("winner defaults to None", s.winner is None)
    check("id defaults to ''", s.id == "")
    check("is FlowState subclass", isinstance(s, DebateState.__bases__[0]))
    check("judge_skill defaults to None", s.judge_skill is None)


# ---------------------------------------------------------------------------
# 2. DebateState – manual assignment works
# ---------------------------------------------------------------------------
def test_debate_state_assign():
    s = DebateState(
        topic="AI Safety",
        total_rounds=3,
        current_round=2,
        current_phase="rebuttal",
        debate_history=[{"debater": "pro_1", "speech": "hello"}],
        paused=True,
        verdict={"winner": "pro"},
        winner="pro",
        id="abc-123",
    )
    check("topic assignment", s.topic == "AI Safety")
    check("total_rounds assignment", s.total_rounds == 3)
    check("current_round assignment", s.current_round == 2)
    check("current_phase assignment", s.current_phase == "rebuttal")
    check("debate_history assignment", s.debate_history == [{"debater": "pro_1", "speech": "hello"}])
    check("paused assignment", s.paused is True)
    check("verdict assignment", s.verdict == {"winner": "pro"})
    check("winner assignment", s.winner == "pro")
    check("id assignment", s.id == "abc-123")


# ---------------------------------------------------------------------------
# 3. SSE event serialization – model_dump_json produces correct `type`
# ---------------------------------------------------------------------------
def test_sse_serialization():
    DID = "debate-001"

    e1 = SSEPhaseStart(debate_id=DID, phase="opening", debater="pro_1", round_num=1)
    data = json.loads(e1.model_dump_json())
    check("SSEPhaseStart type", data["type"] == "phase_start")
    check("SSEPhaseStart debate_id", data["debate_id"] == DID)
    check("SSEPhaseStart phase", data["phase"] == "opening")
    check("SSEPhaseStart round_num", data["round_num"] == 1)

    e2 = SSEThinkingChunk(debate_id=DID, debater="pro_1", content="thinking...")
    data = json.loads(e2.model_dump_json())
    check("SSEThinkingChunk type", data["type"] == "thinking_chunk")
    check("SSEThinkingChunk content", data["content"] == "thinking...")

    e3 = SSESpeechChunk(debate_id=DID, debater="pro_1", content="speech...")
    data = json.loads(e3.model_dump_json())
    check("SSESpeechChunk type", data["type"] == "speech_chunk")

    e4 = SSEPhaseEnd(debate_id=DID, phase="opening", debater="pro_1")
    data = json.loads(e4.model_dump_json())
    check("SSEPhaseEnd type", data["type"] == "phase_end")

    e5 = SSEVerdictChunk(debate_id=DID, content="pro wins", scores={"pro": 8, "con": 6})
    data = json.loads(e5.model_dump_json())
    check("SSEVerdictChunk type", data["type"] == "verdict_chunk")
    check("SSEVerdictChunk scores", data["scores"] == {"pro": 8, "con": 6})

    e6 = SSEPaused(debate_id=DID)
    data = json.loads(e6.model_dump_json())
    check("SSEPaused type", data["type"] == "paused")

    e7 = SSEResumed(debate_id=DID)
    data = json.loads(e7.model_dump_json())
    check("SSEResumed type", data["type"] == "resumed")

    e8 = SSEDebateEnd(debate_id=DID, verdict={"winner": "con", "reason": "better"})
    data = json.loads(e8.model_dump_json())
    check("SSEDebateEnd type", data["type"] == "debate_end")
    check("SSEDebateEnd verdict", data["verdict"]["winner"] == "con")

    e9 = SSEError(debate_id=DID, message="something went wrong")
    data = json.loads(e9.model_dump_json())
    check("SSEError type", data["type"] == "error")
    check("SSEError message", data["message"] == "something went wrong")


# ---------------------------------------------------------------------------
# 4. StartDebateRequest validation (rounds in 1-3)
# ---------------------------------------------------------------------------
def test_start_request_validation():
    # valid
    r = StartDebateRequest(topic="test", rounds=2)
    check("valid request rounds=2", r.rounds == 2)

    r = StartDebateRequest(topic="test", rounds=1)
    check("valid request rounds=1", r.rounds == 1)

    r = StartDebateRequest(topic="test", rounds=3)
    check("valid request rounds=3", r.rounds == 3)

    # invalid – rounds < 1
    from pydantic import ValidationError
    try:
        StartDebateRequest(topic="test", rounds=0)
        check("rounds=0 should fail", False)
    except ValidationError:
        check("rounds=0 raises ValidationError", True)
    except Exception:
        check("rounds=0 raises ValidationError (unexpected)", False)

    # invalid – rounds > 3
    try:
        StartDebateRequest(topic="test", rounds=4)
        check("rounds=4 should fail", False)
    except ValidationError:
        check("rounds=4 raises ValidationError", True)
    except Exception:
        check("rounds=4 raises ValidationError (unexpected)", False)


# ---------------------------------------------------------------------------
# 5. StartDebateResponse
# ---------------------------------------------------------------------------
def test_start_response():
    r = StartDebateResponse(debate_id="d-1")
    check("response debate_id", r.debate_id == "d-1")
    check("response status default", r.status == "running")


# ---------------------------------------------------------------------------
# 6. DebateSummary
# ---------------------------------------------------------------------------
def test_debate_summary():
    s = DebateSummary(
        id="s-1",
        topic="topic",
        total_rounds=2,
        status="completed",
        pro_skills={"debater_1": "munger"},
        con_skills={"debater_1": None},
        verdict={"winner": "pro"},
        winner="pro",
        created_at="2026-01-01T00:00:00",
        finished_at="2026-01-01T01:00:00",
        speeches=[{"debater": "pro_1", "content": "hello"}],
    )
    check("summary id", s.id == "s-1")
    check("summary winner", s.winner == "pro")
    check("summary speeches", s.speeches == [{"debater": "pro_1", "content": "hello"}])
    check("summary format default", s.format == "standard")
    check("summary finished_at", s.finished_at == "2026-01-01T01:00:00")


# ---------------------------------------------------------------------------
# 7. SkillConfig
# ---------------------------------------------------------------------------
def test_skill_config():
    c = SkillConfig()
    check("SkillConfig debater_1 default None", c.debater_1 is None)

    c = SkillConfig(debater_1="skill-a", debater_2="skill-b")
    check("SkillConfig debater_1 assigned", c.debater_1 == "skill-a")
    check("SkillConfig debater_2 assigned", c.debater_2 == "skill-b")
    check("SkillConfig debater_3 default None", c.debater_3 is None)
    check("SkillConfig debater_4 default None", c.debater_4 is None)


# ---------------------------------------------------------------------------
# run all
# ---------------------------------------------------------------------------
def main():
    run_test("DebateState defaults", test_debate_state_defaults)
    run_test("DebateState assignment", test_debate_state_assign)
    run_test("SSE event serialization", test_sse_serialization)
    run_test("StartDebateRequest validation", test_start_request_validation)
    run_test("StartDebateResponse", test_start_response)
    run_test("DebateSummary", test_debate_summary)
    run_test("SkillConfig", test_skill_config)

    print(f"\n{'=' * 40}")
    print(f"  Passed: {passed}  |  Failed: {failed}")
    print(f"{'=' * 40}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
