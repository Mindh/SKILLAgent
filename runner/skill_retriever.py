# -*- coding: utf-8 -*-
"""
skill_retriever.py
──────────────────
RAG 기반 스킬 검색 엔진.

책임:
  1. get_embedding(text)         : 텍스트 → 벡터 (Gemini Embedding API)
  2. ensure_index_ready()        : 캐시 없는 스킬 임베딩 계산 후 JSON 저장
  3. retrieve_top_k_skills(query, k) : 쿼리와 가장 유사한 Top-K 스킬 반환
  4. format_registry_block(skills)   : 라우터 프롬프트용 텍스트 블록 생성

폴백 전략:
  embedding 실패 → keyword 매칭 → 전체 레지스트리 반환
"""

import os
import json
import math
import re
from runner.utils import log

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_JSON_PATH = os.path.join(BASE_DIR, "skills", "skill_registry.json")

# Gemini Embedding API 설정 (지원 모델: gemini-embedding-001, gemini-embedding-2-preview)
EMBEDDING_MODEL = "gemini-embedding-001"
_GEMINI_API_KEY = None   # llm.py와 동일한 키를 런타임에 주입

# ── 인메모리 캐시 (프로세스 수명 동안 유지) ──────────────────────────
_skill_index = None   # [{skill_id, name, description, embedding, ...}]


# ════════════════════════════════════════════════════════════════════
# 내부 유틸리티
# ════════════════════════════════════════════════════════════════════

def _get_api_key() -> str:
    """llm.py의 GEMINI_API_KEY를 가져옵니다."""
    global _GEMINI_API_KEY
    if _GEMINI_API_KEY:
        return _GEMINI_API_KEY
    # llm 모듈을 먼저 import하여 dotenv가 .env를 os.environ에 주입하도록 함.
    try:
        from runner.llm import GEMINI_API_KEY as hardcoded_key
    except ImportError:
        hardcoded_key = ""
    # 환경변수 우선, 없으면 llm.py의 하드코딩된 키 사용
    key = os.environ.get("GEMINI_API_KEY", "") or hardcoded_key
    _GEMINI_API_KEY = key
    return key


def _cosine_similarity(vec_a, vec_b):
    """순수 Python(numpy 없이)으로 코사인 유사도 계산."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _load_registry_json():
    """skill_registry.json을 로드합니다."""
    if not os.path.exists(REGISTRY_JSON_PATH):
        log(f"[Retriever] skill_registry.json 없음: {REGISTRY_JSON_PATH}")
        return []
    with open(REGISTRY_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_registry_json(skills):
    """임베딩이 채워진 스킬 리스트를 skill_registry.json에 저장합니다."""
    with open(REGISTRY_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(skills, f, ensure_ascii=False, indent=2)


# ════════════════════════════════════════════════════════════════════
# 공개 API
# ════════════════════════════════════════════════════════════════════

def get_embedding(text):
    """
    Gemini Embedding API를 호출하여 텍스트 임베딩 벡터를 반환합니다.
    최신 google-genai SDK(google.genai)를 사용합니다.
    실패 시 None을 반환하고 keyword 폴백이 동작합니다.
    """
    try:
        from google import genai
        from google.genai import types
        api_key = _get_api_key()
        if not api_key:
            log("[Retriever] API 키 없음 → 임베딩 폴백")
            return None

        client = genai.Client(api_key=api_key)
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
        )
        return result.embeddings[0].values

    except ImportError:
        log("[Retriever] google-genai 패키지 없음 → keyword 폴백 사용")
        log("[Retriever] 설치: pip install google-genai")
        return None
    except Exception as e:
        log(f"[Retriever] 임베딩 API 실패: {e} → keyword 폴백 사용")
        return None


def ensure_index_ready():
    """
    애플리케이션 시작 시 1회 호출.
    skill_registry.json을 로드하고, embedding=null인 스킬만 임베딩을 시도합니다.
    이미 임베딩된 스킬은 API를 재호출하지 않습니다.
    임베딩 모델이 없어도 JSON 로드까지는 반드시 성공하여 keyword 폴백이 동작합니다.
    """
    global _skill_index

    skills = _load_registry_json()
    if not skills:
        log("[Retriever] 스킬 레지스트리가 비어 있어 인덱스 빌드를 건너뜁니다.")
        _skill_index = []
        return

    # 이미 캐싱된 임베딩 수 확인
    cached_count = sum(1 for s in skills if s.get("embedding") is not None)
    total_count = len(skills)
    log(f"[Retriever] 스킬 {total_count}개 로드됨 (임베딩 캐시: {cached_count}/{total_count})")

    # 임베딩이 없는 스킬만 API 호출 시도 (실패해도 계속 진행)
    updated = False
    for skill in skills:
        if skill.get("embedding") is None:
            try:
                embed_text = (
                    f"{skill.get('name', '')} "
                    f"{skill.get('description', '')} "
                    f"{' '.join(skill.get('trigger_keywords', []))}"
                )
                log(f"[Retriever] '{skill['skill_id']}' 임베딩 계산 시도...")
                vec = get_embedding(embed_text)
                if vec is not None:
                    skill["embedding"] = vec
                    updated = True
                    log(f"[Retriever] '{skill['skill_id']}' 임베딩 완료 (dim={len(vec)})")
                else:
                    log(f"[Retriever] '{skill['skill_id']}' 임베딩 불가 (모델 미설치) -> keyword 폴백 사용")
            except Exception as e:
                log(f"[Retriever] '{skill['skill_id']}' 임베딩 오류: {e} -> 건너뜀")

    if updated:
        try:
            _save_registry_json(skills)
            log("[Retriever] skill_registry.json에 임베딩 캐시 저장 완료")
        except Exception as e:
            log(f"[Retriever] 캐시 저장 실패 (무시됨): {e}")

    _skill_index = skills
    log(f"[Retriever] 인덱스 준비 완료. 총 {total_count}개 스킬 (임베딩: {cached_count + (sum(1 for s in skills if s.get('embedding')) - cached_count)}개)")


def _keyword_fallback(query, skills, k):
    """
    임베딩 없이 trigger_keywords 단순 매칭으로 Top-K 스킬을 반환합니다.
    매칭 없으면 전체 스킬을 반환합니다.
    """
    query_lower = query.lower()
    scored = []
    for skill in skills:
        score = sum(
            1 for kw in skill.get("trigger_keywords", [])
            if kw.lower() in query_lower
        )
        scored.append((score, skill))

    scored.sort(key=lambda x: x[0], reverse=True)

    # 매칭된 스킬이 하나라도 있으면 Top-K 반환, 없으면 전체 반환
    matched = [s for score, s in scored if score > 0]
    if matched:
        return matched[:k]
    return skills  # 전체 폴백


def retrieve_top_k_skills(query: str, k: int = 3, mode: str = "embedding") -> str:
    """
    쿼리에 가장 유사한 Top-K 스킬을 라우터 프롬프트에 주입할 텍스트 블록으로 반환합니다.

    Args:
        query: 사용자 입력 텍스트 (또는 global_state 포함된 조합 문자열)
        k:     반환할 최대 스킬 수
        mode:  'embedding' | 'keyword' | 'full'
    """
    global _skill_index

    # 인덱스가 아직 로드되지 않은 경우 (ensure_index_ready 미호출 환경)
    if _skill_index is None:
        _skill_index = _load_registry_json()

    skills = _skill_index
    if not skills:
        log("[Retriever] 스킬 없음 → 빈 블록 반환")
        return "사용 가능한 스킬이 없습니다."

    # ── mode: full ── 전체 레지스트리를 그대로 포맷팅
    if mode == "full":
        log(f"[Retriever] 'full' 모드: 전체 {len(skills)}개 스킬 반환")
        return format_registry_block(skills)

    # ── mode: keyword ── 키워드 기반 매칭
    if mode == "keyword":
        selected = _keyword_fallback(query, skills, k)
        log(f"[Retriever] 'keyword' 모드: {[s['skill_id'] for s in selected]} 반환")
        return format_registry_block(selected)

    # ── mode: embedding ── 코사인 유사도 기반 Top-K
    # 하나라도 임베딩이 없으면 keyword 폴백
    skills_with_embedding = [s for s in skills if s.get("embedding")]
    if not skills_with_embedding:
        log("[Retriever] 임베딩 벡터 없음 → keyword 폴백")
        selected = _keyword_fallback(query, skills, k)
        return format_registry_block(selected)

    try:
        query_vec = get_embedding(query)
    except Exception:
        query_vec = None
    if query_vec is None:
        log("[Retriever] 쿼리 임베딩 불가 (모델 미설치 또는 API 오류) -> keyword 폴백으로 전환")
        selected = _keyword_fallback(query, skills, k)
        return format_registry_block(selected)

    # 코사인 유사도 계산
    scored = []
    for skill in skills_with_embedding:
        sim = _cosine_similarity(query_vec, skill["embedding"])
        scored.append((sim, skill))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [skill for _, skill in scored[:k]]

    log(f"[Retriever] Top-{k} 검색 결과: {[s['skill_id'] for s in selected]}")
    return format_registry_block(selected)


def format_registry_block(skills):
    """
    스킬 리스트를 router_prompt의 {REGISTRY_CONTENT} 자리에 삽입할
    마크다운 텍스트 블록으로 변환합니다. (기존 skill_registry.md 형식과 동일)
    """
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
    """
    router.py의 valid_ids 하드코딩을 대체.
    skill_registry.json에서 모든 skill_id를 동적으로 반환합니다.
    """
    global _skill_index
    if _skill_index is None:
        _skill_index = _load_registry_json()
    ids = [s["skill_id"] for s in _skill_index if "skill_id" in s]
    # chat은 항상 유효
    if "chat" not in ids:
        ids.append("chat")
    return ids
