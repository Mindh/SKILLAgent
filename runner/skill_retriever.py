# -*- coding: utf-8 -*-
"""
skill_retriever.py
──────────────────
Skill 레지스트리에 대한 얇은 어댑터. 실제 RAG 로직은 runner.retriever.Retriever.

공개 API (후방 호환):
  - get_embedding(text)           : embeddings 모듈로 위임
  - ensure_index_ready()
  - retrieve_top_k_skills(query, k, mode) -> str  (라우터/슈퍼바이저 프롬프트용 텍스트 블록)
  - format_registry_block(skills) -> str
  - get_all_valid_skill_ids()
"""

import os
from runner.utils import log
from runner.retriever import Retriever
from runner.embeddings import get_embedding as _embed

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_JSON_PATH = os.path.join(BASE_DIR, "skills", "skill_registry.json")

_retriever = Retriever(REGISTRY_JSON_PATH, id_field="skill_id", log_tag="SkillRetriever")


def get_embedding(text):
    """후방 호환: embeddings 모듈로 위임."""
    return _embed(text)


def ensure_index_ready():
    _retriever.ensure_index_ready()


def retrieve_top_k_skills(query: str, k: int = 3, mode: str = "embedding") -> str:
    skills = _retriever.retrieve_top_k(query, k=k, mode=mode)
    if not skills:
        log("[SkillRetriever] 스킬 없음 → 빈 블록 반환")
        return "사용 가능한 스킬이 없습니다."
    return format_registry_block(skills)


def format_registry_block(skills) -> str:
    """스킬 리스트 → 라우터/슈퍼바이저 프롬프트에 주입할 마크다운 블록."""
    lines = [
        "라우터는 아래 스킬 목록만 참고하여 다음 액션을 선택한다.",
        "출력은 반드시 아래 목록의 [스킬 ID] 값 하나만이어야 한다.",
        "매칭되는 스킬이 없으면 `chat`을 기본값으로 선택한다.",
        "",
        "## 사용 가능한 스킬 목록",
        "",
    ]
    for i, skill in enumerate(skills, 1):
        skill_id = skill.get("skill_id", "unknown")
        name = skill.get("name", "")
        desc = skill.get("description", "")
        keywords = ", ".join(skill.get("trigger_keywords", []))
        lines.append(f"- **[스킬 ID] {skill_id}** (우선순위: {i})")
        lines.append(f"  - 설명: [{name}] {desc}")
        lines.append(f"  - 트리거 키워드: {keywords}")
        lines.append("")
    return "\n".join(lines)


def get_all_valid_skill_ids():
    """skill_registry.json의 모든 skill_id + 항상 유효한 'chat'."""
    ids = _retriever.get_all_ids()
    if "chat" not in ids:
        ids.append("chat")
    return ids
