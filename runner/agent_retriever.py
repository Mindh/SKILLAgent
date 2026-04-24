# -*- coding: utf-8 -*-
"""
agent_retriever.py
──────────────────
업무 프로세스 Agent 레지스트리용 RAG 검색 엔진.
skill_retriever와 동일한 패턴. 임베딩/유사도 로직은 재사용.

책임:
  1. ensure_agent_index_ready()    : agent_registry.json 로드 + 임베딩 캐시
  2. retrieve_top_k_agents(query)  : Top-K agent 반환 (텍스트 블록)
  3. get_agent_by_id(agent_id)     : agent 전체 정의 로드
  4. load_agent_prompt(agent_id)   : agents/definitions/{id}.md 읽기
"""

import os
import json
from runner.utils import log, load_file
from runner.skill_retriever import (
    get_embedding,
    _cosine_similarity,
    _keyword_fallback,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_REGISTRY_PATH = os.path.join(BASE_DIR, "agents", "agent_registry.json")

_agent_index = None  # 프로세스 수명 동안 유지


def _load_registry():
    if not os.path.exists(AGENT_REGISTRY_PATH):
        log(f"[AgentRetriever] agent_registry.json 없음: {AGENT_REGISTRY_PATH}")
        return []
    with open(AGENT_REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_registry(agents):
    with open(AGENT_REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(agents, f, ensure_ascii=False, indent=2)


def ensure_agent_index_ready():
    """애플리케이션 시작 시 1회 호출. 임베딩 없는 agent만 계산 후 캐시."""
    global _agent_index

    agents = _load_registry()
    if not agents:
        log("[AgentRetriever] 등록된 agent 없음")
        _agent_index = []
        return

    cached = sum(1 for a in agents if a.get("embedding") is not None)
    total = len(agents)
    log(f"[AgentRetriever] agent {total}개 로드됨 (임베딩 캐시: {cached}/{total})")

    updated = False
    for agent in agents:
        if agent.get("embedding") is None:
            try:
                embed_text = (
                    f"{agent.get('name', '')} "
                    f"{agent.get('description', '')} "
                    f"{' '.join(agent.get('trigger_keywords', []))}"
                )
                log(f"[AgentRetriever] '{agent['agent_id']}' 임베딩 계산 시도...")
                vec = get_embedding(embed_text)
                if vec is not None:
                    agent["embedding"] = vec
                    updated = True
                    log(f"[AgentRetriever] '{agent['agent_id']}' 임베딩 완료 (dim={len(vec)})")
                else:
                    log(f"[AgentRetriever] '{agent['agent_id']}' 임베딩 불가 → keyword 폴백")
            except Exception as e:
                log(f"[AgentRetriever] '{agent['agent_id']}' 임베딩 오류: {e}")

    if updated:
        try:
            _save_registry(agents)
            log("[AgentRetriever] agent_registry.json 캐시 저장 완료")
        except Exception as e:
            log(f"[AgentRetriever] 캐시 저장 실패: {e}")

    _agent_index = agents


def _ensure_loaded():
    global _agent_index
    if _agent_index is None:
        _agent_index = _load_registry()


def retrieve_top_k_agents(query: str, k: int = 3, mode: str = "embedding") -> list:
    """
    쿼리와 유사한 Top-K agent를 dict 리스트로 반환.
    supervisor 프롬프트에서 자체 포매팅하므로 텍스트가 아닌 리스트 반환.
    """
    _ensure_loaded()
    agents = _agent_index
    if not agents:
        return []

    if mode == "full":
        return agents[:k] if k < len(agents) else agents

    if mode == "keyword":
        return _keyword_fallback(query, agents, k)

    # embedding 모드
    with_embed = [a for a in agents if a.get("embedding")]
    if not with_embed:
        log("[AgentRetriever] 임베딩 없음 → keyword 폴백")
        return _keyword_fallback(query, agents, k)

    try:
        qvec = get_embedding(query)
    except Exception:
        qvec = None
    if qvec is None:
        log("[AgentRetriever] 쿼리 임베딩 실패 → keyword 폴백")
        return _keyword_fallback(query, agents, k)

    scored = [(_cosine_similarity(qvec, a["embedding"]), a) for a in with_embed]
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [a for _, a in scored[:k]]
    log(f"[AgentRetriever] Top-{k} agent: {[a['agent_id'] for a in selected]}")
    return selected


def format_agents_block(agents: list) -> str:
    """supervisor 프롬프트에 주입할 agent 후보 마크다운 블록."""
    if not agents:
        return "(사용 가능한 agent 없음)"
    lines = ["## 사용 가능한 업무 Agent 후보", ""]
    for i, a in enumerate(agents, 1):
        workflow_preview = ", ".join(step.get("name", step.get("id", "")) for step in a.get("workflow", [])[:4])
        remaining = len(a.get("workflow", [])) - 4
        if remaining > 0:
            workflow_preview += f", ...(+{remaining})"
        lines.append(f"- **[agent_id] {a.get('agent_id')}** (우선순위: {i})")
        lines.append(f"  - 이름: {a.get('name','')}")
        lines.append(f"  - 설명: {a.get('description','')}")
        lines.append(f"  - 단계: {workflow_preview}")
        lines.append("")
    return "\n".join(lines)


def get_agent_by_id(agent_id: str):
    _ensure_loaded()
    for a in _agent_index:
        if a.get("agent_id") == agent_id:
            return a
    return None


def get_all_agent_ids() -> list:
    _ensure_loaded()
    return [a["agent_id"] for a in _agent_index if "agent_id" in a]


def load_agent_prompt(agent_id: str) -> str:
    """agents/definitions/{agent_id}.md 전체 읽기."""
    return load_file(f"agents/definitions/{agent_id}.md")
