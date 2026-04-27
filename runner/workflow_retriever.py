# -*- coding: utf-8 -*-
"""
워크플로우 검색기.

agent_registry.json의 trigger_keywords(키워드 매칭) 또는
캐시된 embedding(시맨틱 검색)으로 관련 워크플로우를 찾는다.
임베딩 API를 사용할 수 없으면 키워드 매칭으로 자동 폴백.
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


def retrieve_workflows(query: str, k: int = 2) -> List[str]:
    """
    query와 관련된 상위 k개 워크플로우의 agent_id 목록을 반환한다.
    매칭되는 워크플로우가 없으면 빈 리스트를 반환한다.

    검색 우선순위:
      1. 임베딩 시맨틱 검색 (registry에 embedding 캐시가 있을 때)
      2. 키워드 매칭 (trigger_keywords 기반, 항상 사용 가능)
    """
    registry = _load_registry()

    # 모든 항목에 임베딩이 캐시돼 있으면 시맨틱 검색 시도
    if all(item.get("embedding") for item in registry):
        results = _embedding_search(query, registry, k)
        if results:
            return results

    return _keyword_search(query, registry, k)


def load_workflow_definition(agent_id: str) -> str:
    """agents/definitions/{agent_id}.md 파일을 읽어 반환한다."""
    return load_file(f"agents/definitions/{agent_id}.md")


# ── 검색 구현 ─────────────────────────────────────────────────────────────────

def _keyword_search(query: str, registry: list, k: int) -> List[str]:
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


def _embedding_search(query: str, registry: list, k: int) -> List[str]:
    try:
        import os
        from google import genai

        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
        response = client.models.embed_content(
            model="gemini-embedding-001",
            contents=query,
        )
        query_vec = response.embeddings[0].values

        scored = []
        for item in registry:
            emb = item.get("embedding")
            if emb:
                score = _cosine(query_vec, emb)
                scored.append((score, item["agent_id"]))
        scored.sort(reverse=True)

        # 유사도가 너무 낮으면 관련 없음으로 처리 (임계값 0.5)
        result = [agent_id for score, agent_id in scored[:k] if score >= 0.5]
        if result:
            log(f"[WorkflowRetriever] 임베딩 검색: {result}")
        return result

    except Exception as e:
        log(f"[WorkflowRetriever] 임베딩 검색 실패, 키워드로 폴백: {e}")
        return []


def _cosine(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0
