# -*- coding: utf-8 -*-
"""
embeddings.py
─────────────
임베딩과 유사도 계산을 한 곳에 모은 공용 모듈.

공개 API:
  - get_api_key()            : Gemini API 키 (환경변수 또는 .env)
  - get_embedding(text)      : 텍스트 → 벡터 (실패 시 None)
  - cosine_similarity(a, b)  : 코사인 유사도 (numpy 미사용)
  - embedding_available()    : 임베딩 모델을 쓸 수 있는 환경인지 시작 시 1회 감지 후 캐시
"""

import os
import math
from runner.utils import log

EMBEDDING_MODEL = "gemini-embedding-001"

# ── 내부 캐시 ──────────────────────────────────────────────
_API_KEY = None
_EMBEDDING_AVAILABLE = None  # None=미감지, True/False=감지 결과


def get_api_key() -> str:
    """API 키 조회. llm 모듈을 먼저 import하여 dotenv 로드를 보장."""
    global _API_KEY
    if _API_KEY:
        return _API_KEY
    try:
        from runner.llm import GEMINI_API_KEY as hardcoded_key
    except ImportError:
        hardcoded_key = ""
    _API_KEY = os.environ.get("GEMINI_API_KEY", "") or hardcoded_key
    return _API_KEY


def cosine_similarity(vec_a, vec_b) -> float:
    """순수 Python 코사인 유사도. 한쪽이 0벡터면 0.0."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def get_embedding(text: str):
    """
    Gemini Embedding API 호출. 실패 시 None.
    실패 사유에 따라 _EMBEDDING_AVAILABLE 상태도 갱신한다.
    """
    global _EMBEDDING_AVAILABLE
    api_key = get_api_key()
    if not api_key:
        log("[Embeddings] API 키 없음 → 임베딩 사용 불가")
        _EMBEDDING_AVAILABLE = False
        return None

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        log("[Embeddings] google-genai 패키지 없음 → 임베딩 사용 불가 (pip install google-genai)")
        _EMBEDDING_AVAILABLE = False
        return None

    try:
        client = genai.Client(api_key=api_key)
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        # 첫 호출 성공 시 가용성 True로 고정
        if _EMBEDDING_AVAILABLE is None:
            _EMBEDDING_AVAILABLE = True
        return result.embeddings[0].values
    except Exception as e:
        log(f"[Embeddings] 임베딩 API 호출 실패: {e}")
        # 한 번이라도 명시적으로 실패하면 false로 (가용성 체크용)
        if _EMBEDDING_AVAILABLE is None:
            _EMBEDDING_AVAILABLE = False
        return None


def embedding_available() -> bool:
    """
    임베딩 사용 가능 여부. 미감지 상태면 짧은 probe 1회로 확인.
    한 번 감지된 결과는 프로세스 수명 동안 캐시.
    """
    global _EMBEDDING_AVAILABLE
    if _EMBEDDING_AVAILABLE is not None:
        return _EMBEDDING_AVAILABLE
    # probe
    log("[Embeddings] 가용성 probe 실행")
    vec = get_embedding("probe")
    if vec is None:
        _EMBEDDING_AVAILABLE = False
    else:
        _EMBEDDING_AVAILABLE = True
    log(f"[Embeddings] embedding_available = {_EMBEDDING_AVAILABLE}")
    return _EMBEDDING_AVAILABLE
