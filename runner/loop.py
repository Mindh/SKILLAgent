# -*- coding: utf-8 -*-
"""
Agentic 루프 — 프롬프트 기반 도구 호출 방식 (ReAct-style).

function calling을 지원하지 않는 모델에서도 동작한다.
모델이 응답 안에 <tool_call> 블록을 포함하면 루프가 이를 파싱해 도구를 실행하고,
결과를 messages에 주입한 뒤 모델을 재호출한다.

LLM 호출은 모두 runner.llm.call_ai()를 통해서만 수행한다.
모델·엔드포인트·SDK를 바꿀 때는 runner/llm.py만 수정하면 된다.

Phase 1 변경:
- 한 응답에서 **여러 개의 <tool_call> 블록**을 추출해 순차 실행 (re.findall 기반)
- 각 호출에 자동 부여되는 `call_id` (예: i1c1, i1c2, i2c1) — 결과·오류 메시지에 1:1 매핑
- ```tool_call ... ``` / ```json ... ``` 코드펜스로 감싸도 파싱 가능
- 호출 직전 `validate_args()`로 필수 파라미터 검증 → 실패 시 모델에 교정 피드백
"""
import json
import re
from typing import List, Optional, Tuple

from runner import skill_loader
from runner.llm import call_ai
from runner.tools import execute_tool, validate_args
from runner.utils import cached_file, log
from runner.workflow_retriever import retrieve_workflows

# 모델이 한 응답에 도구 호출만 반복하는 것을 방지하는 사이클 한도
# (한 사이클 = call_ai 1회 + 그 응답의 모든 tool_call 실행)
MAX_TOOL_CALLS = 5

# 한 turn 전체에서 실행 가능한 도구 호출 총량 (다중 호출 누적 폭주 방지)
MAX_TOTAL_TOOL_RUNS = 15

_system_prompt_cache = None  # type: Optional[str]


def _get_system_prompt():
    """system_prompt.md를 로드해 반환한다. (도구 목록은 포함하지 않음)"""
    global _system_prompt_cache
    if _system_prompt_cache is None:
        _system_prompt_cache = cached_file("prompts/system_prompt.md")
    return _system_prompt_cache


def turn(user_input, messages_or_state, injected_workflows=None):
    """
    단일 사용자 턴을 실행한다.

    호출 형태 (둘 다 지원):
      A) state dict: turn(user_input, state)
         - state = {"messages": [...], "injected_workflows": set, "active_subagent": None|dict, ...}
      B) 레거시 위치 인자: turn(user_input, messages, injected_workflows)
         - state는 내부적으로 임시 dict로 만들어진다.
    반환값: AI의 최종 텍스트 응답 (사용자에게 노출할 본문).
    """
    state = _coerce_state(messages_or_state, injected_workflows)
    messages = state["messages"]

    # ⓪ 서브에이전트가 활성화돼 있으면 입력을 위임
    if state.get("active_subagent"):
        return _route_to_subagent(user_input, state)

    # ① 도구 카테고리 요약을 첫 턴에만 주입 (Phase 2: progressive disclosure)
    if not messages:
        catalog = skill_loader.category_summary_markdown()
        messages.append({
            "role": "user",
            "content": catalog,
        })
        messages.append({
            "role": "assistant",
            "content": "네, 도구 카테고리를 확인했습니다. 필요할 때 list_skills로 펼쳐 사용하겠습니다.",
        })
        log("[Loop] 도구 카테고리 요약 주입 완료")

    # ② 워크플로우 매칭 → 자동 위임 (Phase 3)
    # 부모 messages에 워크플로우 정의를 텍스트 주입하지 않고, 서브에이전트로 격리 실행.
    matched = retrieve_workflows(user_input, k=1, skip_llm_classify=False)
    if matched:
        wf_id = matched[0]
        log("[Loop] 워크플로우 매칭 → 서브에이전트 위임: {}".format(wf_id))
        return _start_subagent_and_route(wf_id, user_input, state)

    messages.append({"role": "user", "content": user_input})

    system_prompt = _get_system_prompt()

    # ③ 프롬프트 기반 도구 호출 루프
    total_runs = 0
    for cycle in range(MAX_TOOL_CALLS + 1):
        user_prompt = _serialize_messages(messages)
        text = call_ai(system_prompt, user_prompt, temperature=0)
        log("[Loop] cycle={}".format(cycle))

        # ④ 모든 <tool_call> 블록 추출
        tool_calls = _extract_tool_calls(text)

        if not tool_calls:
            # 도구 호출 없음 → 최종 응답
            messages.append({"role": "assistant", "content": text})
            return text

        # call_id 자동 부여 (사이클 + 인덱스)
        for idx, tc in enumerate(tool_calls, 1):
            if not tc.get("call_id"):
                tc["call_id"] = "i{}c{}".format(cycle, idx)

        # ⑤ 사이클 내 모든 호출을 순차 실행
        for tc in tool_calls:
            if total_runs >= MAX_TOTAL_TOOL_RUNS:
                log("[Loop] 총 호출 한도 도달 — 잔여 호출 스킵")
                break
            total_runs += 1
            _run_single_call(tc, messages)

    return "처리 중 도구 호출 한도에 도달했습니다."


def _run_single_call(tc, messages):
    """
    단일 도구 호출 1건을 실행하고 결과(또는 오류)를 messages에 주입한다.
    호출/결과 메시지에 #call_id를 포함시켜 다중 호출 시 1:1 매핑이 가능하게 한다.
    """
    name = tc.get("name", "") or ""
    args = tc.get("args") or {}
    call_id = tc.get("call_id", "c0")

    # 검증 — 실패 시 호출 자체를 시도하지 않고 모델에 교정 피드백
    ok, err = validate_args(name, args)

    # 호출 시도 마커는 검증 결과와 무관하게 남긴다 (UI·디버그용)
    messages.append({
        "role": "assistant",
        "content": "[도구 호출: {} #{}]".format(name, call_id),
    })

    if not ok:
        log("[Loop] 검증 실패 #{}: {}".format(call_id, err))
        messages.append({
            "role": "user",
            "content": (
                "[도구 오류: {} #{}]\n{}\n\n"
                "위 오류를 참고해 올바른 인자로 다시 호출하거나, "
                "정보가 부족하면 사용자에게 자연스러운 한국어로 물어보세요. "
                "동일 오류로 무한 재시도하지 마세요."
            ).format(name, call_id, err),
        })
        return

    # 실행
    log("[Loop] 도구 호출 #{}: {}({})".format(call_id, name, args))
    try:
        result = execute_tool(name, args)
    except Exception as e:
        result = {"error": str(e)}
    log("[Loop] 도구 결과 #{}: {}".format(call_id, str(result)[:200]))

    result_str = (
        json.dumps(result, ensure_ascii=False)
        if not isinstance(result, str)
        else result
    )
    messages.append({
        "role": "user",
        "content": (
            "[도구 실행 결과: {} #{}]\n{}\n\n"
            "위 결과를 사용자에게 자연스러운 한국어로 전달하세요.\n\n"
            "⚠️ 핵심 규칙:\n"
            "- 결과의 핵심 정보를 반드시 메시지에 포함시켜야 합니다.\n"
            "- 결과 없이 다음 단계로 넘어가거나 추가 질문만 하지 마세요.\n"
            "- 워크플로우 진행 중이라면 '결과 알림 → 다음 단계 안내'를 한 메시지에 함께 담으세요.\n"
            "- JSON, 코드 블록(```), 키-값 원본을 그대로 출력하지 마세요. (단, HTML 도구 결과는 그대로 전달)\n"
            "- 숫자나 목록은 자연스럽게 풀어쓰세요 (예: \"홍길동 님의 잔여 휴가는 12일입니다\").\n"
            "- 추가 도구가 필요하면 <tool_call> 형식으로 다음 호출을 하세요. "
            "**여러 도구를 한 응답에 동시에 호출**해도 됩니다. 결과를 모두 받은 뒤 종합 답변하세요.\n"
            "- 도구 결과가 HTML 문서인 경우(<!DOCTYPE html>로 시작) HTML 전체를 그대로 응답에 포함시키세요. "
            "시스템이 자동으로 미리보기 렌더링합니다."
        ).format(name, call_id, result_str),
    })


def _coerce_state(messages_or_state, injected_workflows):
    """
    레거시 호출 형태(messages, injected_workflows)와 신규 형태(state dict)를 모두 받아
    표준화된 state dict로 반환한다.
    """
    if isinstance(messages_or_state, dict) and "messages" in messages_or_state:
        state = messages_or_state
    else:
        state = {
            "messages": messages_or_state if isinstance(messages_or_state, list) else [],
            "injected_workflows": injected_workflows or set(),
        }
    state.setdefault("messages", [])
    state.setdefault("injected_workflows", set())
    state.setdefault("active_subagent", None)
    state.setdefault("subagent_history", [])
    state.setdefault("last_tool_events", [])
    state.setdefault("last_artifacts", [])
    return state


def _start_subagent_and_route(workflow_id, user_input, state):
    """워크플로우 매칭 직후 서브에이전트를 새로 만들고 첫 입력을 처리한다."""
    # 순환 import 방지: 함수 내부에서 import
    from runner import subagent

    # 부모 messages에 위임 시작 마커 (web.py가 SSE 이벤트로 변환)
    state["messages"].append({
        "role": "user",
        "content": user_input,
    })
    state["messages"].append({
        "role": "assistant",
        "content": "[워크플로우 위임 시작: {}]".format(workflow_id),
    })

    sub_state, result = subagent.start(workflow_id, user_input)
    state["active_subagent"] = sub_state
    return _absorb_subagent_result(result, state)


def _route_to_subagent(user_input, state):
    """이미 활성화된 서브에이전트로 사용자 입력 전달."""
    from runner import subagent

    sub_state = state["active_subagent"]
    state["messages"].append({"role": "user", "content": user_input})
    result = subagent.handle_user_input(sub_state, user_input)
    return _absorb_subagent_result(result, state)


def _absorb_subagent_result(result, state):
    """
    서브에이전트의 1턴 결과를 부모 컨텍스트에 흡수.
    - text는 부모 messages의 assistant 응답으로 추가 (사용자가 보는 그대로)
    - 도구 이벤트와 아티팩트는 state에 임시 저장 (web.py가 SSE 변환에 사용)
    - done=True면 active_subagent를 비우고 요약 마커 추가
    """
    text = result.get("text", "") or ""
    state["messages"].append({"role": "assistant", "content": text})
    state["last_tool_events"] = result.get("tool_events", [])
    state["last_artifacts"] = result.get("artifacts", [])

    if result.get("done"):
        sub = state.get("active_subagent") or {}
        state["active_subagent"] = None
        summary = result.get("summary") or "워크플로우 종료"
        wf_id = sub.get("workflow_id", "")
        steps = sub.get("step_count", 0)
        tools_used = sub.get("tools_used", [])
        # 부모 messages에 요약만 1줄 (중간 단계는 격리 → 컨텍스트 절감)
        state["messages"].append({
            "role": "user",
            "content": "[워크플로우 위임 종료: {} | steps={} | tools={} | summary={}]".format(
                wf_id, steps, len(tools_used), summary
            ),
        })
        state["subagent_history"].append({
            "workflow_id": wf_id,
            "summary": summary,
            "step_count": steps,
            "tools_used": tools_used,
        })
        log("[Loop] 서브에이전트 종료: {} (steps={})".format(wf_id, steps))
    return text


def _serialize_messages(messages):
    """
    대화 히스토리(messages 리스트)를 단일 문자열로 직렬화한다.
    call_ai(system_prompt, user_prompt)의 user_prompt 인자로 전달하기 위함.

    각 메시지는 [USER] / [ASSISTANT] 헤더와 함께 구분되어 모델이 turn 구조를
    인식할 수 있도록 한다.
    """
    parts = []
    for m in messages:
        role = m.get("role", "user").upper()
        content = m.get("content", "")
        parts.append("[{}]\n{}".format(role, content))
    return "\n\n".join(parts)


# ── tool_call 파싱 ────────────────────────────────────────────────────────────

# 1순위: <tool_call>...</tool_call>
_TC_TAG_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL | re.IGNORECASE)
# 2순위: ```tool_call ... ``` (`tool_call` 펜스 라벨)
_TC_FENCE_LABELED_RE = re.compile(
    r"```\s*tool_call\s*\n?(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
# 3순위: ```json ... ``` 안에 {"name": ..., "args": ...} 형태가 있을 때만
_TC_FENCE_JSON_RE = re.compile(
    r"```\s*(?:json|JSON)\s*\n?(\{.*?\})\s*\n?```",
    re.DOTALL,
)


def _extract_tool_calls(text):
    """
    응답 텍스트에서 모든 도구 호출을 추출해 list로 반환한다.

    파싱 우선순위:
      1. <tool_call>...</tool_call> 태그 (권장 형식)
      2. ```tool_call ... ``` 펜스
      3. ```json ... ``` 펜스 안의 {"name":..., "args":...} 객체

    각 항목은 {"name": str, "args": dict, "call_id": str?} 형태.
    파싱 실패 시 빈 리스트 반환.
    """
    # type: (str) -> List[dict]
    if not text:
        return []
    calls = []
    for m in _TC_TAG_RE.finditer(text):
        parsed = _try_parse_tool_block(m.group(1))
        if parsed:
            calls.append(parsed)
    if calls:
        return calls

    # 태그가 없으면 펜스 폴백
    for m in _TC_FENCE_LABELED_RE.finditer(text):
        parsed = _try_parse_tool_block(m.group(1))
        if parsed:
            calls.append(parsed)
    if calls:
        return calls

    for m in _TC_FENCE_JSON_RE.finditer(text):
        parsed = _try_parse_tool_block(m.group(1))
        if parsed:
            calls.append(parsed)
    return calls


def _try_parse_tool_block(raw):
    """
    문자열에서 도구 호출 JSON을 파싱해 정규화된 dict로 반환.
    실패 시 None.

    허용:
      - 순수 JSON: {"name": "...", "args": {...}}
      - args 대신 arguments 키 사용
      - 코드펜스로 한 번 더 감싸진 경우 자동 벗김
    """
    if not raw:
        return None
    s = raw.strip()
    # 내부에 또 한 번 ``` 펜스가 있을 수 있음
    inner_fence = re.match(r"```(?:[a-zA-Z_]+)?\s*\n?(.*?)\n?```", s, re.DOTALL)
    if inner_fence:
        s = inner_fence.group(1).strip()
    # JSON 본체 추출 (최외곽 중괄호 균형 매칭)
    json_str = _extract_first_json_object(s)
    if not json_str:
        return None
    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if "name" not in data:
        return None
    # arguments → args 별칭 흡수
    if "args" not in data and "arguments" in data:
        data["args"] = data.pop("arguments")
    if "args" not in data:
        data["args"] = {}
    if not isinstance(data["args"], dict):
        return None
    return data


def _extract_first_json_object(s):
    """문자열에서 첫 번째로 등장하는 균형 잡힌 {...} 블록을 반환. 없으면 None."""
    # type: (str) -> Optional[str]
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
    return None
