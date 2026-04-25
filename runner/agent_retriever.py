# -*- coding: utf-8 -*-
"""
agent_retriever.py
──────────────────
Agent 레지스트리에 대한 얇은 어댑터. 실제 RAG 로직은 runner.retriever.Retriever.

공개 API (후방 호환):
  - ensure_agent_index_ready()
  - retrieve_top_k_agents(query, k, mode) -> list[dict]
  - format_agents_block(agents) -> str
  - get_agent_by_id(agent_id) -> dict | None
  - get_all_agent_ids() -> list[str]
  - load_agent_prompt(agent_id) -> str
"""

import os
from runner.utils import cached_file
from runner.retriever import Retriever

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_REGISTRY_PATH = os.path.join(BASE_DIR, "agents", "agent_registry.json")

_retriever = Retriever(AGENT_REGISTRY_PATH, id_field="agent_id", log_tag="AgentRetriever")


def ensure_agent_index_ready():
    _retriever.ensure_index_ready()


def retrieve_top_k_agents(query: str, k: int = 3, mode: str = "embedding") -> list:
    """supervisor 프롬프트에서 자체 포매팅하므로 dict 리스트 반환."""
    return _retriever.retrieve_top_k(query, k=k, mode=mode)


def format_agents_block(agents: list) -> str:
    """supervisor 프롬프트에 주입할 agent 후보 마크다운 블록."""
    if not agents:
        return "(사용 가능한 agent 없음)"
    lines = ["## 사용 가능한 업무 Agent 후보", ""]
    for i, a in enumerate(agents, 1):
        workflow = a.get("workflow", [])
        preview = ", ".join(step.get("name", step.get("id", "")) for step in workflow[:4])
        remaining = len(workflow) - 4
        if remaining > 0:
            preview += f", ...(+{remaining})"
        lines.append(f"- **[agent_id] {a.get('agent_id')}** (우선순위: {i})")
        lines.append(f"  - 이름: {a.get('name','')}")
        lines.append(f"  - 설명: {a.get('description','')}")
        lines.append(f"  - 단계: {preview}")
        lines.append("")
    return "\n".join(lines)


def get_agent_by_id(agent_id: str):
    return _retriever.get_by_id(agent_id)


def get_all_agent_ids() -> list:
    return _retriever.get_all_ids()


def load_agent_prompt(agent_id: str) -> str:
    """agents/definitions/{agent_id}.md 전체 읽기."""
    return cached_file(f"agents/definitions/{agent_id}.md")
