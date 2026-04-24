# -*- coding: utf-8 -*-
"""
agent_runner.py
───────────────
Active agent의 한 턴 실행.

흐름:
  1. agent 정의(prompt) + 현재 진행 상태 + 사용자 입력을 조합하여 LLM 호출
  2. 응답 JSON 파싱 (message, step_completed, collected, next_action, skill_call)
  3. next_action == "call_skill" → components.run_skill 실행 후 결과를 다시 주입하고 재호출 (최대 1회)
  4. 진행 상태 업데이트 후 결과 반환

반환: {
  "message": str,
  "next_action": "ask_user" | "call_skill" | "done" | "bubble_up",
  "updated_agent_state": dict,      # 갱신된 active_agent 상태
  "skill_result": dict | None,      # call_skill이 있었던 경우 결과
}
"""

import json
from runner.utils import load_file, log, parse_json, build_chat_history
from runner.llm import call_ai
from runner.components import run_skill
from runner.agent_retriever import get_agent_by_id, load_agent_prompt


MAX_SKILL_CHAINS = 2  # 한 턴에 agent가 연쇄적으로 skill을 호출하는 최대 횟수


def _build_agent_user_prompt(
    agent_def: dict,
    agent_state: dict,
    user_input: str,
    history: list,
    last_skill_result: dict = None,
) -> str:
    workflow_block = json.dumps(agent_def.get("workflow", []), ensure_ascii=False, indent=2)
    completed = agent_state.get("completed_steps", [])
    collected = agent_state.get("collected_data", {})

    parts = []
    parts.append(f"[Workflow 전체 정의]\n```json\n{workflow_block}\n```\n")
    parts.append(f"[완료된 단계]\n{completed if completed else '(없음)'}\n")
    parts.append(
        f"[수집된 정보]\n```json\n{json.dumps(collected, ensure_ascii=False, indent=2)}\n```\n"
    )
    if last_skill_result is not None:
        parts.append(
            f"[최근 스킬 결과]\n```json\n{json.dumps(last_skill_result, ensure_ascii=False, indent=2)}\n```\n"
        )
    if history:
        parts.append(f"[최근 대화]\n{build_chat_history(history)}\n")
    parts.append(f"[직원 입력]\n{user_input}\n")
    parts.append("\n[출력] 위 지침에 따라 JSON 하나만 출력하라.")
    return "\n".join(parts)


def _call_agent_llm(agent_def: dict, agent_state: dict, user_input: str,
                    history: list, config: dict, last_skill_result=None) -> dict:
    agent_id = agent_def["agent_id"]
    base_system = load_file("prompts/base_system.md")
    agent_prompt = load_agent_prompt(agent_id)
    system = f"{base_system}\n\n---\n{agent_prompt}"

    user_prompt = _build_agent_user_prompt(
        agent_def, agent_state, user_input, history, last_skill_result
    )

    raw = call_ai(system_prompt=system, user_prompt=user_prompt, temperature=config.get("temperature", 0))
    log(f"[AgentRunner:{agent_id}] 원본 응답: {raw[:300]}")

    parsed = parse_json(raw)
    if isinstance(parsed, dict) and "_parse_error" in parsed:
        log(f"[AgentRunner:{agent_id}] JSON 파싱 실패 → bubble_up 복구")
        return {
            "message": raw.strip() or "죄송합니다. 방금 답변을 정리하지 못했습니다.",
            "step_completed": None,
            "collected": {},
            "next_action": "bubble_up",
            "skill_call": None,
        }

    # 기본값 보정
    parsed.setdefault("message", "")
    parsed.setdefault("step_completed", None)
    parsed.setdefault("collected", {})
    parsed.setdefault("next_action", "ask_user")
    parsed.setdefault("skill_call", None)
    return parsed


def _apply_agent_update(agent_state: dict, agent_response: dict) -> dict:
    """agent_response의 step_completed / collected를 상태에 머지."""
    new_state = {
        "agent_id": agent_state.get("agent_id"),
        "status": agent_state.get("status", "active"),
        "completed_steps": list(agent_state.get("completed_steps", [])),
        "collected_data": dict(agent_state.get("collected_data", {})),
    }
    step = agent_response.get("step_completed")
    if step and step not in new_state["completed_steps"]:
        new_state["completed_steps"].append(step)
    new_state["collected_data"].update(agent_response.get("collected", {}) or {})
    return new_state


def step(active_agent: dict, user_input: str, history: list, config: dict) -> dict:
    """
    Active agent로 한 턴 실행. call_skill 체이닝 포함.
    반환 딕셔너리:
      - message / next_action / updated_agent_state / skill_result
    """
    agent_id = active_agent["agent_id"]
    agent_def = get_agent_by_id(agent_id)
    if agent_def is None:
        log(f"[AgentRunner] 알 수 없는 agent: {agent_id}")
        return {
            "message": "죄송합니다. 해당 업무 프로세스를 찾을 수 없습니다.",
            "next_action": "bubble_up",
            "updated_agent_state": active_agent,
            "skill_result": None,
        }

    state = active_agent
    last_skill_result = None

    for chain in range(MAX_SKILL_CHAINS + 1):
        resp = _call_agent_llm(agent_def, state, user_input, history, config, last_skill_result)
        state = _apply_agent_update(state, resp)

        next_action = resp.get("next_action", "ask_user")

        if next_action == "call_skill":
            sc = resp.get("skill_call") or {}
            skill_id = (sc.get("skill_id") or "").strip()
            skill_user_input = sc.get("user_input") or user_input

            allowed = agent_def.get("allowed_skills", [])
            if skill_id not in allowed:
                log(f"[AgentRunner:{agent_id}] 허용되지 않은 skill 호출: {skill_id} (allowed={allowed})")
                return {
                    "message": resp.get("message") or f"'{skill_id}' 스킬을 호출할 권한이 이 업무에 없습니다.",
                    "next_action": "bubble_up",
                    "updated_agent_state": state,
                    "skill_result": None,
                }

            if chain >= MAX_SKILL_CHAINS:
                log(f"[AgentRunner:{agent_id}] skill 체이닝 상한 도달")
                return {
                    "message": resp.get("message") or "연속 스킬 호출 한도에 도달했습니다.",
                    "next_action": "ask_user",
                    "updated_agent_state": state,
                    "skill_result": last_skill_result,
                }

            log(f"[AgentRunner:{agent_id}] 스킬 호출: {skill_id}")
            _, raw_out = run_skill(skill_id, skill_user_input, config)
            parsed_out = parse_json(raw_out)
            last_skill_result = parsed_out if isinstance(parsed_out, dict) else {"raw": raw_out}

            # 스킬 결과를 주입하고 agent 재호출 (다음 루프 반복)
            continue

        # ask_user / done / bubble_up: 종료
        return {
            "message": resp.get("message", ""),
            "next_action": next_action,
            "updated_agent_state": state,
            "skill_result": last_skill_result,
        }

    # 안전 폴백 (도달 불가)
    return {
        "message": "",
        "next_action": "ask_user",
        "updated_agent_state": state,
        "skill_result": last_skill_result,
    }
