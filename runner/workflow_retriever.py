# -*- coding: utf-8 -*-
"""
워크플로우 검색기.

2단계 분류:
  1) 키워드 매칭 — agent_registry.json의 trigger_keywords substring 매칭 (빠르고 결정적)
  2) 매칭 실패 시 LLM 분류기 — call_ai로 모든 워크플로우 description을 보여주고 적합한 ID 선택

명백한 chat 발화("안녕?")는 LLM이 'none'을 반환하므로 자연스럽게 빈 리스트가 됨.
임베딩 검색은 사용하지 않음 (false-positive 잦고 의존성 부담).
"""
import json
import os
from typing import List, Optional

from runner.utils import load_file, log

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REGISTRY_PATH = os.path.join(BASE_DIR, "agents", "agent_registry.json")

_registry_cache: Optional[list] = None


def _load_registry() -> list:
    global _registry_cache
    if _registry_cache is None:
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
            _registry_cache = json.load(f)
    return _registry_cache


def retrieve_workflows(query: str, k: int = 1) -> List[str]:
    """
    query에 가장 적합한 워크플로우 ID를 최대 k개 반환한다.
    매칭되는 워크플로우가 없으면 빈 리스트.

    검색 순서:
      1) 키워드 매칭 (trigger_keywords substring) — 매치 있으면 즉시 반환
      2) LLM 분류 (description 기반) — 키워드 매치 없을 때만 호출
    """
    registry = _load_registry()

    # 1차: 키워드 매칭
    keyword_results = _keyword_search(query, registry, k)
    if keyword_results:
        return keyword_results

    # 2차: LLM 분류
    return _llm_classify(query, registry, k)


def load_workflow_definition(agent_id: str) -> str:
    """agents/definitions/{agent_id}.md 파일을 읽어 반환한다."""
    return load_file(f"agents/definitions/{agent_id}.md")


# ── 검색 구현 ─────────────────────────────────────────────────────────────────

def _keyword_search(query: str, registry: list, k: int) -> List[str]:
    """trigger_keywords substring 매칭. 점수 높은 순으로 최대 k개 반환."""
    query_lower = query.lower()
    scored = []
    for item in registry:
        score = sum(
            1 for kw in item.get("trigger_keywords", [])
            if kw.lower() in query_lower
        )
        if score > 0:
            scored.append((score, item["agent_id"]))
    scored.sort(reverse=True)
    result = [agent_id for _, agent_id in scored[:k]]
    if result:
        log(f"[WorkflowRetriever] 키워드 매칭: {result}")
    return result


def _llm_classify(query: str, registry: list, k: int) -> List[str]:
    """
    LLM에 모든 워크플로우 description을 보여주고 적합한 ID 1개를 선택하게 한다.
    적합한 것이 없으면 'none'을 반환하도록 지시.

    LLM 호출은 runner.llm.call_ai()를 통해 수행되므로 자체 모델 환경에서도 동작.
    """
    # 순환 import 방지: 함수 내에서 import
    from runner.llm import call_ai

    options = "\n".join(
        f"- {item['agent_id']}: {item.get('description', '').strip()}"
        for item in registry
    )

    system_prompt = (
        "당신은 사용자 발화를 분석해 가장 적합한 HR 워크플로우를 선택하는 분류기입니다.\n"
        "아래 목록 중 하나의 워크플로우 ID를 반환하거나, 어떤 것도 적합하지 않으면 'none'을 반환합니다.\n\n"
        f"[사용 가능한 워크플로우]\n{options}\n\n"
        "[응답 규칙]\n"
        "- 정확히 워크플로우 ID 하나만 출력 (예: leave_intake)\n"
        "- 인사·감사·일반 잡담 등 적합한 워크플로우가 없으면 정확히 'none' 출력\n"
        "- 그 외 어떤 텍스트, 설명, 코드블록, JSON도 출력하지 마세요"
    )

    try:
        response = call_ai(system_prompt, f"사용자 발화: {query}").strip().lower()
    except Exception as e:
        log(f"[WorkflowRetriever] LLM 분류기 호출 실패: {e}")
        return []

    valid_ids = {item["agent_id"].lower() for item in registry}
    if response in valid_ids:
        log(f"[WorkflowRetriever] LLM 분류: {response}")
        # registry에서 원본 대소문자 ID 찾아 반환
        for item in registry:
            if item["agent_id"].lower() == response:
                return [item["agent_id"]][:k]
    log(f"[WorkflowRetriever] LLM 판단: 매칭 없음 ({response[:50]!r})")
    return []
