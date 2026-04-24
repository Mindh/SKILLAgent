# -*- coding: utf-8 -*-
"""
supervisor.py
─────────────
세션의 최상위 오케스트레이터.

매 턴 진입점: turn(user_input, session, config) -> dict
  · active/paused agent 상태를 보고 적절한 action을 LLM으로 결정
  · 4가지 action(continue_agent / switch_agent / call_skill / chat) 디스패치
  · agent_runner의 bubble_up 신호를 받으면 같은 턴 내에서 supervisor 재진입 (1회)
"""

import json
from runner.utils import load_file, log, parse_json, build_chat_history
from runner.llm import call_ai
from runner.components import run_skill
from runner.skill_retriever import retrieve_top_k_skills
from runner.agent_retriever import (
    retrieve_top_k_agents,
    format_agents_block,
    get_agent_by_id,
    get_all_agent_ids,
)
from runner import agent_runner


MAX_BUBBLE_UP_RECURSION = 1


# ──────────────────────────────────────────────────────────────
# 세션 초기화
# ──────────────────────────────────────────────────────────────
def _ensure_session(session: dict) -> dict:
    session.setdefault("active_agent", None)      # {agent_id, status, completed_steps, collected_data}
    session.setdefault("paused_agents", [])       # list of active_agent snapshots
    session.setdefault("global_state", {})
    session.setdefault("history", [])
    session.setdefault("pending_switch", None)    # {"target": agent_id} — 사용자 승인 대기
    return session


# ──────────────────────────────────────────────────────────────
# Supervisor 의사결정 (LLM)
# ──────────────────────────────────────────────────────────────
def _summarize_active_agent(active: dict) -> str:
    if not active:
        return "(없음)"
    agent_def = get_agent_by_id(active["agent_id"])
    workflow = agent_def.get("workflow", []) if agent_def else []
    completed = active.get("completed_steps", [])
    remaining = [s.get("id") for s in workflow if s.get("id") not in completed]
    return json.dumps({
        "agent_id": active["agent_id"],
        "name": agent_def.get("name") if agent_def else "",
        "status": active.get("status", "active"),
        "completed_steps": completed,
        "remaining_steps": remaining,
        "collected_data_keys": list(active.get("collected_data", {}).keys()),
    }, ensure_ascii=False, indent=2)


def _build_supervisor_input(user_input: str, session: dict, config: dict) -> str:
    active = session.get("active_agent")
    paused = session.get("paused_agents", [])
    pending = session.get("pending_switch")
    history = session.get("history", [])

    top_k_agents = retrieve_top_k_agents(
        user_input,
        k=config.get("agent_retrieval_top_k", 3),
        mode=config.get("skill_retrieval_mode", "embedding"),
    )
    agents_block = format_agents_block(top_k_agents)

    skills_block = retrieve_top_k_skills(
        user_input,
        k=config.get("skill_retrieval_top_k", 3),
        mode=config.get("skill_retrieval_mode", "embedding"),
    )

    parts = []
    parts.append(f"[Active Agent]\n```json\n{_summarize_active_agent(active)}\n```\n")
    if paused:
        parts.append(
            f"[Paused Agents]\n"
            + ", ".join(p.get("agent_id", "?") for p in paused) + "\n"
        )
    else:
        parts.append("[Paused Agents]\n(없음)\n")
    if pending:
        parts.append(
            f"[전환 승인 대기 중]\n"
            f"사용자에게 '{pending.get('target')}' agent로 전환할지 방금 물어봤다. "
            f"이번 턴의 사용자 입력이 긍정/부정인지 판단하고, "
            f"긍정이면 action=switch_agent, target='{pending.get('target')}', user_confirmed=true로 출력하라. "
            f"부정이면 action=continue_agent(또는 chat), reason에 '사용자 전환 거부'.\n"
        )
    parts.append(f"\n{agents_block}\n")
    parts.append(f"\n{skills_block}\n")
    if history:
        parts.append(f"[최근 대화]\n{build_chat_history(history)}\n")
    parts.append(f"\n[사용자 입력]\n{user_input}")
    return "\n".join(parts)


def _decide(user_input: str, session: dict, config: dict) -> dict:
    base_system = load_file("prompts/base_system.md")
    template = load_file("prompts/supervisor_prompt.md")
    sup_input = _build_supervisor_input(user_input, session, config)
    prompt = template.replace("{SUPERVISOR_INPUT}", sup_input)

    raw = call_ai(system_prompt=base_system, user_prompt=prompt, temperature=config.get("temperature", 0))
    log(f"[Supervisor] 원본 응답: {raw[:300]}")
    parsed = parse_json(raw)
    if isinstance(parsed, dict) and "_parse_error" in parsed:
        log("[Supervisor] JSON 파싱 실패 → chat 폴백")
        return {
            "action": "chat", "target": None, "reason": "파싱 실패",
            "user_confirm_needed": False, "user_confirmed": False, "resume_hint_after": False,
        }

    parsed.setdefault("action", "chat")
    parsed.setdefault("target", None)
    parsed.setdefault("reason", "")
    parsed.setdefault("user_confirm_needed", False)
    parsed.setdefault("user_confirmed", False)
    parsed.setdefault("resume_hint_after", False)

    if parsed["action"] not in {"continue_agent", "switch_agent", "call_skill", "chat"}:
        log(f"[Supervisor] 알 수 없는 action '{parsed['action']}' → chat")
        parsed["action"] = "chat"

    log(f"[Supervisor] 결정: {parsed}")
    return parsed


# ──────────────────────────────────────────────────────────────
# Action executors
# ──────────────────────────────────────────────────────────────
def _resume_hint(active: dict) -> str:
    if not active:
        return ""
    agent_def = get_agent_by_id(active["agent_id"])
    name = agent_def.get("name") if agent_def else active["agent_id"]
    return f"\n\n(진행 중이던 '{name}' 업무를 이어서 진행할까요?)"


def _do_continue_agent(user_input: str, session: dict, config: dict, depth: int = 0) -> str:
    active = session.get("active_agent")
    if not active:
        return _do_chat(user_input, session, config)

    result = agent_runner.step(active, user_input, session.get("history", []), config)
    session["active_agent"] = result["updated_agent_state"]
    session["active_agent"]["status"] = "active"

    if result["next_action"] == "bubble_up":
        if depth >= MAX_BUBBLE_UP_RECURSION:
            log("[Supervisor] bubble_up 재귀 한도 도달 → 현재 메시지 반환")
            return result["message"] or "다시 말씀해 주시겠어요?"
        log("[Supervisor] agent bubble_up → supervisor 재진입")
        # active_agent를 paused로 바꾸진 않고 그대로 두되, 재결정에 넘김
        return _dispatch(user_input, session, config, depth=depth + 1)

    if result["next_action"] == "done":
        log(f"[Supervisor] agent '{active['agent_id']}' 완료 → 세션 해제")
        session["active_agent"] = None

    return result["message"]


def _do_switch_agent(target_id: str, user_input: str, session: dict, config: dict, depth: int = 0) -> str:
    if target_id not in get_all_agent_ids():
        log(f"[Supervisor] 잘못된 agent 전환 대상: {target_id} → chat 폴백")
        return _do_chat(user_input, session, config)

    current = session.get("active_agent")
    if current and current.get("agent_id") != target_id:
        paused_snapshot = dict(current)
        paused_snapshot["status"] = "paused"
        session["paused_agents"].append(paused_snapshot)
        log(f"[Supervisor] '{current['agent_id']}' → paused_agents로 이동")

    # 이미 동일 agent면 그대로 continue
    if current and current.get("agent_id") == target_id:
        session["active_agent"]["status"] = "active"
    else:
        # 이전에 pause된 같은 agent가 있으면 복원, 아니면 신규
        resumed = None
        for i, p in enumerate(session["paused_agents"]):
            if p.get("agent_id") == target_id:
                resumed = session["paused_agents"].pop(i)
                break
        if resumed:
            resumed["status"] = "active"
            session["active_agent"] = resumed
            log(f"[Supervisor] paused agent '{target_id}' 복원")
        else:
            session["active_agent"] = {
                "agent_id": target_id,
                "status": "active",
                "completed_steps": [],
                "collected_data": {},
            }
            log(f"[Supervisor] 신규 agent '{target_id}' 활성화")

    # 새 agent의 첫 step 실행
    return _do_continue_agent(user_input, session, config, depth=depth)


def _do_call_skill(skill_id: str, user_input: str, session: dict, config: dict) -> str:
    log(f"[Supervisor] 단발 skill 호출: {skill_id}")
    if skill_id == "chat" or not skill_id:
        return _do_chat(user_input, session, config)

    try:
        _, raw_out = run_skill(skill_id, user_input, config)
    except Exception as e:
        log(f"[Supervisor] skill 호출 실패: {e}")
        return _do_chat(user_input, session, config)

    parsed = parse_json(raw_out)
    session["global_state"][skill_id] = parsed if isinstance(parsed, dict) else raw_out

    return _format_skill_response(skill_id, parsed, raw_out)


def _format_skill_response(skill_id: str, parsed, raw: str) -> str:
    """단발 skill 결과를 사람이 읽기 좋은 텍스트로."""
    if isinstance(parsed, dict):
        if "_parse_error" in parsed:
            return raw.strip()
        if "function_result" in parsed:
            fr = parsed["function_result"]
            if isinstance(fr, (dict, list)):
                return f"결과:\n```json\n{json.dumps(fr, ensure_ascii=False, indent=2)}\n```"
            return f"결과: {fr}"
        if "response" in parsed:
            return parsed["response"]
        if "translated" in parsed:
            return f"번역 결과: {parsed['translated']}"
        if "summary" in parsed:
            return f"요약: {parsed['summary']}"
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    return str(parsed or raw).strip()


def _do_chat(user_input: str, session: dict, config: dict) -> str:
    base_system = load_file("prompts/base_system.md")
    history = session.get("history", [])
    if history:
        prompt = f"[최근 대화]\n{build_chat_history(history)}\n\n[사용자 입력]\n{user_input}"
    else:
        prompt = user_input
    return call_ai(system_prompt=base_system, user_prompt=prompt, temperature=config.get("temperature", 0))


# ──────────────────────────────────────────────────────────────
# 턴 디스패치
# ──────────────────────────────────────────────────────────────
def _dispatch(user_input: str, session: dict, config: dict, depth: int = 0) -> str:
    decision = _decide(user_input, session, config)
    action = decision["action"]
    target = decision.get("target")
    pending = session.get("pending_switch")

    # pending_switch가 있는 상태에서 사용자가 부정/무관 응답을 하면 pending 해제
    if pending and not (action == "switch_agent" and decision.get("user_confirmed")):
        log("[Supervisor] pending_switch 해제 (사용자 거부 또는 다른 요청)")
        session["pending_switch"] = None

    # switch_agent + 사용자 확인 승인 → 실제 전환 수행
    if action == "switch_agent" and decision.get("user_confirmed") and pending:
        return _do_switch_agent(pending["target"], user_input, session, config, depth=depth)

    # switch_agent + 확인 필요 → 질문만 하고 pending 기록
    if action == "switch_agent" and decision.get("user_confirm_needed"):
        current = session.get("active_agent")
        target_def = get_agent_by_id(target) if target else None
        target_name = target_def.get("name") if target_def else target
        current_def = get_agent_by_id(current["agent_id"]) if current else None
        current_name = current_def.get("name") if current_def else ""
        session["pending_switch"] = {"target": target}
        if current_name:
            return f"현재 '{current_name}' 업무를 잠시 중단하고 '{target_name}'(으)로 전환할까요?"
        return f"'{target_name}' 업무로 시작할까요?"

    if action == "switch_agent":
        return _do_switch_agent(target, user_input, session, config, depth=depth)

    if action == "continue_agent":
        return _do_continue_agent(user_input, session, config, depth=depth)

    if action == "call_skill":
        msg = _do_call_skill(target, user_input, session, config)
        if decision.get("resume_hint_after") and session.get("active_agent"):
            msg += _resume_hint(session["active_agent"])
        return msg

    # chat
    msg = _do_chat(user_input, session, config)
    if decision.get("resume_hint_after") and session.get("active_agent"):
        msg += _resume_hint(session["active_agent"])
    return msg


# ──────────────────────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────────────────────
def turn(user_input: str, session: dict, config: dict) -> dict:
    """
    한 턴 실행. 반환: {"message": str, "session": session}
    session은 in-place 업데이트되지만 명시적으로도 돌려줌.
    """
    _ensure_session(session)
    if not user_input or not user_input.strip():
        return {"message": "입력이 비어 있습니다.", "session": session}

    try:
        message = _dispatch(user_input, session, config, depth=0)
    except Exception as e:
        log(f"[Supervisor] 디스패치 중 예외: {e}")
        message = "죄송합니다. 요청 처리 중 문제가 발생했어요. 다시 시도해 주세요."

    # 세션 history 갱신
    session.setdefault("history", []).append({"user": user_input, "ai": message})
    return {"message": message, "session": session}
