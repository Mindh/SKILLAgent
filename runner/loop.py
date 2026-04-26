# -*- coding: utf-8 -*-
"""
Agentic 루프 — 프롬프트 기반 도구 호출 방식 (ReAct-style).

function calling을 지원하지 않는 모델에서도 동작한다.
모델이 응답 안에 <tool_call> 블록을 포함하면 루프가 이를 파싱해 도구를 실행하고,
결과를 messages에 주입한 뒤 모델을 재호출한다.
"""
import json
import os
import re
import time

import openai

# MODEL_NAME·API_KEY 설정은 llm.py에서 단일 관리.
# 모델/엔드포인트를 바꿀 때는 llm.py의 값만 수정하면 된다.
from runner.llm import MODEL_NAME, GEMINI_API_KEY
from runner.tools import execute_tool, get_tool_descriptions
from runner.utils import cached_file, log
from runner.workflow_retriever import retrieve_workflows, load_workflow_definition

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# llm.py와 동일한 OpenAI-compatible 엔드포인트
_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# 단일 턴에서 허용하는 최대 도구 호출 횟수 (무한 루프 방지)
MAX_TOOL_CALLS = 5

_system_prompt_cache: str | None = None


def _get_system_prompt() -> str:
    """system_prompt.md를 로드해 반환한다. (도구 목록은 포함하지 않음)"""
    global _system_prompt_cache
    if _system_prompt_cache is None:
        _system_prompt_cache = cached_file("prompts/system_prompt.md")
    return _system_prompt_cache


def _get_client() -> openai.OpenAI:
    key = os.environ.get("GEMINI_API_KEY", GEMINI_API_KEY)
    if not key:
        raise ValueError(
            "API 키가 설정되지 않았습니다. runner/llm.py 또는 환경변수 GEMINI_API_KEY를 설정해주세요."
        )
    return openai.OpenAI(api_key=key, base_url=_BASE_URL)


def turn(user_input: str, messages: list, injected_workflows: set) -> str:
    """
    단일 사용자 턴을 실행한다.

    - messages: 전체 대화 히스토리 (호출자가 유지, 이 함수가 in-place로 갱신).
    - injected_workflows: 이미 주입된 워크플로우 ID 집합 (호출자가 유지).
    - 반환값: AI의 최종 텍스트 응답.
    """
    # ① 도구 목록을 첫 턴에만 주입 (시스템 프롬프트 과부하 방지)
    if not messages:
        tool_desc = get_tool_descriptions()
        messages.append({
            "role": "user",
            "content": f"[사용 가능한 도구 목록]\n{tool_desc}",
        })
        messages.append({
            "role": "assistant",
            "content": "네, 사용 가능한 도구 목록을 확인했습니다.",
        })
        log("[Loop] 도구 목록 주입 완료")

    # ② 관련 워크플로우 검색 및 주입 (user 메시지 추가 전)
    for wf_id in retrieve_workflows(user_input, k=2):
        if wf_id not in injected_workflows:
            definition = load_workflow_definition(wf_id)
            messages.append({
                "role": "user",
                "content": f"[워크플로우 컨텍스트 로드: {wf_id}]\n{definition}",
            })
            messages.append({
                "role": "assistant",
                "content": "네, 해당 워크플로우 절차를 참고하겠습니다.",
            })
            injected_workflows.add(wf_id)
            log(f"[Loop] 워크플로우 주입: {wf_id}")

    messages.append({"role": "user", "content": user_input})

    client = _get_client()
    system_prompt = _get_system_prompt()

    # ③ 프롬프트 기반 도구 호출 루프
    for iteration in range(MAX_TOOL_CALLS + 1):
        start = time.time()
        # system 역할을 지원하지 않는 모델을 위해
        # 시스템 프롬프트를 첫 번째 user/assistant 교환으로 주입한다.
        full_messages = [
            {"role": "user",      "content": f"[System Instructions]\n{system_prompt}"},
            {"role": "assistant", "content": "네, 이해했습니다. 지시사항을 따르겠습니다."},
        ] + messages

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=full_messages,
            temperature=0,
        )
        log(f"[Loop] API 응답: {time.time() - start:.2f}초 (iteration={iteration})")

        text = response.choices[0].message.content or ""

        # ④ <tool_call> 블록 감지
        tool_call = _extract_tool_call(text)

        if tool_call is None:
            # 도구 호출 없음 → 최종 응답만 messages에 저장
            messages.append({"role": "assistant", "content": text})
            return text

        # ⑤ 중간 응답: raw <tool_call> 대신 요약 텍스트로 저장
        # (다음 턴에서 모델이 <tool_call> 패턴을 무한 반복하는 것을 방지)
        name = tool_call.get("name", "")
        args = tool_call.get("args", {})
        messages.append({
            "role": "assistant",
            "content": f"[도구 호출: {name}]",
        })

        # ⑥ 도구 실행
        log(f"[Loop] 도구 호출: {name}({args})")
        try:
            result = execute_tool(name, args)
        except Exception as e:
            result = {"error": str(e)}
        log(f"[Loop] 도구 결과: {str(result)[:200]}")

        # ⑦ 결과를 messages에 주입하고 재호출
        result_str = (
            json.dumps(result, ensure_ascii=False)
            if not isinstance(result, str)
            else result
        )
        messages.append({
            "role": "user",
            "content": (
                f"[도구 실행 결과: {name}]\n{result_str}\n\n"
                "위 결과를 바탕으로 사용자에게 자연스러운 한국어로 응답하세요. "
                "추가 도구가 필요하면 <tool_call> 형식으로 호출하세요."
            ),
        })

    return "처리 중 도구 호출 한도에 도달했습니다."


def _extract_tool_call(text: str) -> dict | None:
    """
    응답 텍스트에서 <tool_call> 블록을 추출한다.
    블록이 없거나 파싱 실패 시 None 반환.
    """
    match = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
        if "name" in data and "args" in data:
            return data
    except (json.JSONDecodeError, KeyError):
        pass
    return None
