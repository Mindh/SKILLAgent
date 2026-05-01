# -*- coding: utf-8 -*-
"""
In-process 서브에이전트 — 워크플로우를 격리된 messages·자체 ReAct 루프로 실행한다.

설계 원칙:
- 부모와 같은 Python 프로세스, 같은 `call_ai()` 사용 (자체 호스팅 모델 제약 충족)
- 부모 messages를 참조하지 않음 — 서브에이전트는 자체 messages 리스트만 보유
- 부모는 사용자 입력을 그대로 전달, 서브에이전트의 응답은 그대로 부모 → 사용자에게 노출
- 종료 신호: 응답에 `<workflow_complete>요약</workflow_complete>` 태그가 있거나 max_turns 도달
- 종료 시 부모 messages에는 한 줄 요약(또는 명시 요약 + 회수된 아티팩트)만 추가 → 컨텍스트 절감

부모 입장에서 본 인터페이스:
    state['active_subagent'] = start(workflow_id, initial_user_input)
    while True:
        result = handle_user_input(state['active_subagent'], next_user_input)
        # result: {"text": "...", "done": bool, "summary": str?, "artifacts": [...]?}

상태 dict 구조:
    {
        "workflow_id": str,
        "display_ko": str,
        "messages": list,       # 자체 대화 히스토리
        "step_count": int,      # 누적 ReAct 사이클
        "max_turns": int,
        "tools_used": list,     # 누적 사용 도구 이름 (중복 포함)
        "artifacts": list,      # 회수된 산출물 (HTML 등)
    }
"""
import json
import re
from datetime import datetime

from runner import skill_loader
from runner.llm import call_ai
from runner.loop import (
    MAX_TOTAL_TOOL_RUNS as PARENT_MAX_TOTAL_TOOL_RUNS,  # noqa: F401 (참조용)
    _extract_tool_calls,
    _serialize_messages,
)
from runner.tools import execute_tool, validate_args
from runner.utils import cached_file, log
from runner.workflow_retriever import load_workflow_body, load_workflow_meta


# 한 번의 user 입력에 대해 서브에이전트가 돌릴 최대 ReAct 사이클 (안전장치)
SUBAGENT_CYCLES_PER_INPUT = 5

# 한 사이클 내 도구 호출 한도
SUBAGENT_MAX_TOOLS_PER_CYCLE = 8

# <workflow_complete> 태그 추출
_COMPLETE_RE = re.compile(
    r"<workflow_complete>(.*?)</workflow_complete>",
    re.DOTALL | re.IGNORECASE,
)

# HTML 아티팩트 추출 (회수용)
_HTML_RE = re.compile(
    r"(<!DOCTYPE\s+html[^>]*>.*?</html>|<html[^>]*>.*?</html>)",
    re.DOTALL | re.IGNORECASE,
)

_BASE_PERSONA_CACHE = None


def _base_persona():
    """부모와 동일한 system_prompt.md를 베이스 페르소나로 재사용."""
    global _BASE_PERSONA_CACHE
    if _BASE_PERSONA_CACHE is None:
        _BASE_PERSONA_CACHE = cached_file("prompts/system_prompt.md")
    return _BASE_PERSONA_CACHE


def _build_subagent_system_prompt(workflow_id, body):
    """
    서브에이전트의 system prompt:
      - 베이스 페르소나(system_prompt.md)
      - 워크플로우 본문 정의
      - 종료 규약 안내 (<workflow_complete>)
    """
    completion_rule = (
        "\n\n---\n\n"
        "# 워크플로우 종료 규약 (필수)\n\n"
        "이 워크플로우의 모든 단계가 끝났다고 판단되면 응답 마지막에 다음 태그를 정확히 포함하세요:\n"
        "```\n"
        "<workflow_complete>한 줄 요약 (예: 김철수 님 휴직 접수 완료, 발령일 2025-04-15)</workflow_complete>\n"
        "```\n"
        "- 태그가 없으면 사용자 입력을 계속 기다린다.\n"
        "- 사용자가 명백히 다른 주제로 넘어가면 마무리 인사 후 태그 출력.\n"
        "- 태그 본문은 사용자에게 직접 보이지 않으므로 한 줄 요약만 적으면 된다.\n"
    )
    return _base_persona() + (
        "\n\n---\n\n"
        "# 현재 워크플로우 (격리 실행 중)\n\n"
        "워크플로우 ID: `{wf}`\n\n"
        "{body}"
    ).format(wf=workflow_id, body=(body or "").strip()) + completion_rule


def _initial_catalog_message(categories):
    """
    서브에이전트의 첫 사용자 메시지: 도구 카탈로그 요약 + 워크플로우 관련 카테고리 강조.
    workflow.frontmatter.categories에 명시된 카테고리는 schema 상세까지 즉시 펼쳐 노출,
    나머지는 카테고리 인덱스만 보여주고 list_skills로 펼치게 한다.
    """
    summary = skill_loader.category_summary_markdown()
    if not categories:
        return summary
    expanded_blocks = []
    for cat in categories:
        items = skill_loader.list_skills_in_category(cat)
        if not items:
            continue
        lines = ["[자동 펼침: {} 카테고리]".format(cat)]
        for it in items:
            params = it.get("parameters", {}).get("properties", {})
            required = it.get("parameters", {}).get("required", [])
            lines.append("- **{}** — {}".format(it["name"], it.get("description", "")))
            for k, v in params.items():
                marker = "(필수)" if k in required else "(선택)"
                lines.append("    - {} {}: {}".format(k, marker, v.get("description", "")))
        expanded_blocks.append("\n".join(lines))
    return summary + "\n\n" + "\n\n".join(expanded_blocks)


# ── 라이프사이클 API ────────────────────────────────────────────────────────

def start(workflow_id, initial_user_input):
    """
    서브에이전트 상태 dict를 만들고 첫 사용자 입력을 처리한다.

    반환: (state_dict, result_dict)
      result_dict 구조는 handle_user_input과 동일.
    """
    meta = load_workflow_meta(workflow_id) or {}
    body = load_workflow_body(workflow_id)
    state = {
        "workflow_id": workflow_id,
        "display_ko": meta.get("display_ko", workflow_id),
        "categories": meta.get("categories", []),
        "max_turns": int(meta.get("max_turns") or 15),
        "messages": [],
        "step_count": 0,
        "tools_used": [],
        "artifacts": [],
        "started_at": datetime.utcnow().isoformat() + "Z",
        "system_prompt": _build_subagent_system_prompt(workflow_id, body),
    }
    # 첫 메시지: 카탈로그 + 자동 펼침
    catalog_msg = _initial_catalog_message(state["categories"])
    state["messages"].append({"role": "user", "content": catalog_msg})
    state["messages"].append({
        "role": "assistant",
        "content": "네, 워크플로우 절차와 도구 카탈로그를 확인했습니다.",
    })
    log("[Subagent] 시작: workflow={}".format(workflow_id))
    return state, handle_user_input(state, initial_user_input)


def handle_user_input(state, user_input):
    """
    사용자 입력 1건을 받아 서브에이전트의 ReAct 사이클들을 돌리고
    최종 사용자 노출 텍스트를 반환한다.

    반환:
      {
        "text": str,          # 사용자에게 노출할 본문 (workflow_complete 태그 제거됨)
        "done": bool,         # 워크플로우가 종료되었는지
        "summary": str|None,  # done=True일 때 <workflow_complete> 본문
        "tool_events": list,  # [{phase, tool_name, call_id, result?, ...}] — 부모 SSE에 노출
        "artifacts": list,    # 이번 입력에서 새로 회수된 아티팩트 (HTML 등)
      }
    """
    if user_input is not None and str(user_input).strip():
        state["messages"].append({"role": "user", "content": user_input})

    tool_events = []
    new_artifacts = []

    for cycle in range(SUBAGENT_CYCLES_PER_INPUT):
        if state["step_count"] >= state["max_turns"]:
            log("[Subagent] max_turns 도달 → 강제 종료")
            forced = "워크플로우 최대 진행 횟수에 도달했습니다. 안전을 위해 여기서 마무리합니다."
            state["messages"].append({"role": "assistant", "content": forced})
            return {
                "text": forced,
                "done": True,
                "summary": "max_turns 도달로 강제 종료",
                "tool_events": tool_events,
                "artifacts": new_artifacts,
            }

        state["step_count"] += 1
        user_prompt = _serialize_messages(state["messages"])
        text = call_ai(state["system_prompt"], user_prompt, temperature=0)
        log("[Subagent] cycle={} step_count={}".format(cycle, state["step_count"]))

        tool_calls = _extract_tool_calls(text)

        if not tool_calls:
            # 텍스트만 있는 응답 → 사용자에게 노출
            state["messages"].append({"role": "assistant", "content": text})
            display_text, summary, done = _split_completion(text)
            html = _HTML_RE.search(display_text or "")
            if html:
                new_artifacts.append({"type": "html", "content": html.group(1)})
            state["artifacts"].extend(new_artifacts)
            return {
                "text": display_text,
                "done": done,
                "summary": summary,
                "tool_events": tool_events,
                "artifacts": new_artifacts,
            }

        # 다중 도구 호출 처리
        for idx, tc in enumerate(tool_calls, 1):
            if not tc.get("call_id"):
                tc["call_id"] = "s{}c{}".format(state["step_count"], idx)

        runs = 0
        for tc in tool_calls:
            if runs >= SUBAGENT_MAX_TOOLS_PER_CYCLE:
                log("[Subagent] 사이클 내 도구 호출 한도 초과 → 잔여 스킵")
                break
            runs += 1
            evt = _run_single_call_subagent(tc, state)
            tool_events.extend(evt)
            if tc.get("name"):
                state["tools_used"].append(tc["name"])

    # 사이클 한도 초과
    log("[Subagent] SUBAGENT_CYCLES_PER_INPUT 초과 → 종료 없이 반환")
    fallback = "처리 중 도구 호출 한도에 도달했습니다. 다시 한 번 알려주시면 이어서 진행하겠습니다."
    state["messages"].append({"role": "assistant", "content": fallback})
    return {
        "text": fallback,
        "done": False,
        "summary": None,
        "tool_events": tool_events,
        "artifacts": new_artifacts,
    }


def _split_completion(text):
    """
    응답에서 <workflow_complete>...</workflow_complete> 태그를 분리.
    반환: (display_text_without_tag, summary_or_none, done_flag)
    """
    if not text:
        return text, None, False
    m = _COMPLETE_RE.search(text)
    if not m:
        return text, None, False
    summary = m.group(1).strip()
    cleaned = (text[:m.start()] + text[m.end():]).strip()
    return cleaned, summary, True


def _run_single_call_subagent(tc, state):
    """
    단일 도구 호출 1건을 실행하고 결과/오류를 서브에이전트 messages에 주입.
    부모 SSE에 노출할 이벤트 리스트(짧은) 반환.
    """
    name = tc.get("name", "") or ""
    args = tc.get("args") or {}
    call_id = tc.get("call_id", "c0")
    events = []

    ok, err = validate_args(name, args)
    state["messages"].append({
        "role": "assistant",
        "content": "[도구 호출: {} #{}]".format(name, call_id),
    })

    if not ok:
        log("[Subagent] 검증 실패 #{}: {}".format(call_id, err))
        state["messages"].append({
            "role": "user",
            "content": (
                "[도구 오류: {} #{}]\n{}\n\n"
                "위 오류를 참고해 올바른 인자로 다시 호출하거나 사용자에게 추가 정보를 요청하세요."
            ).format(name, call_id, err),
        })
        events.append({
            "phase": "tool_result",
            "tool_name": name,
            "call_id": call_id,
            "result": err[:300],
            "is_error": True,
        })
        return events

    log("[Subagent] 도구 호출 #{}: {}({})".format(call_id, name, args))
    events.append({
        "phase": "tool_call",
        "tool_name": name,
        "call_id": call_id,
    })
    try:
        result = execute_tool(name, args)
    except Exception as e:
        result = {"error": str(e)}
    log("[Subagent] 도구 결과 #{}: {}".format(call_id, str(result)[:200]))

    result_str = (
        json.dumps(result, ensure_ascii=False)
        if not isinstance(result, str)
        else result
    )
    state["messages"].append({
        "role": "user",
        "content": (
            "[도구 실행 결과: {} #{}]\n{}\n\n"
            "위 결과를 사용자에게 자연스러운 한국어로 전달하세요. "
            "결과의 핵심 정보를 반드시 포함하고, 다음 단계가 필요하면 이어서 안내하세요. "
            "워크플로우 모든 단계가 끝났다면 응답 마지막에 <workflow_complete>요약</workflow_complete> 태그를 포함하세요."
        ).format(name, call_id, result_str),
    })
    # 결과 미리보기는 짧게 (HTML/긴 JSON은 부모 UI에서 그대로 노출 X)
    preview = result_str[:300]
    events.append({
        "phase": "tool_result",
        "tool_name": name,
        "call_id": call_id,
        "result": preview,
        "is_error": False,
    })
    return events
