# -*- coding: utf-8 -*-
"""
retriever.py
────────────
제네릭 Top-K RAG 엔진. skill/agent 레지스트리에 모두 사용된다.

각 도메인의 어댑터는 Retriever 인스턴스를 만들어 사용한다:
  - registry_path: JSON 파일 경로
  - id_field:      각 항목을 식별하는 필드명 (예: "skill_id", "agent_id")
  - log_tag:       로그 메시지 태그
"""

import os
import json
from runner.utils import log
from runner.embeddings import (
    get_embedding,
    cosine_similarity,
    embedding_available,
)


class Retriever:
    def __init__(self, registry_path: str, id_field: str, log_tag: str = "Retriever"):
        self.registry_path = registry_path
        self.id_field = id_field
        self.tag = log_tag
        self._index = None  # list[dict] | None

    # ── 내부 I/O ─────────────────────────────────────────────
    def _load(self):
        if not os.path.exists(self.registry_path):
            log(f"[{self.tag}] 레지스트리 없음: {self.registry_path}")
            return []
        with open(self.registry_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, items):
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

    def _ensure_loaded(self):
        if self._index is None:
            self._index = self._load()

    # ── 공개 API ─────────────────────────────────────────────
    def ensure_index_ready(self):
        """시작 시 1회 호출. embedding=null인 항목만 임베딩 시도 후 캐시."""
        items = self._load()
        if not items:
            log(f"[{self.tag}] 레지스트리 비어 있음")
            self._index = []
            return

        cached = sum(1 for x in items if x.get("embedding") is not None)
        total = len(items)
        log(f"[{self.tag}] {total}개 로드됨 (임베딩 캐시: {cached}/{total})")

        if not embedding_available():
            log(f"[{self.tag}] 임베딩 불가 환경 → keyword 모드로 동작")
            self._index = items
            return

        updated = False
        for item in items:
            if item.get("embedding") is not None:
                continue
            item_id = item.get(self.id_field, "?")
            try:
                embed_text = (
                    f"{item.get('name', '')} "
                    f"{item.get('description', '')} "
                    f"{' '.join(item.get('trigger_keywords', []))}"
                )
                log(f"[{self.tag}] '{item_id}' 임베딩 계산 시도...")
                vec = get_embedding(embed_text)
                if vec is not None:
                    item["embedding"] = vec
                    updated = True
                    log(f"[{self.tag}] '{item_id}' 임베딩 완료 (dim={len(vec)})")
                else:
                    log(f"[{self.tag}] '{item_id}' 임베딩 불가 → keyword 폴백")
            except Exception as e:
                log(f"[{self.tag}] '{item_id}' 임베딩 오류: {e}")

        if updated:
            try:
                self._save(items)
                log(f"[{self.tag}] 임베딩 캐시 저장 완료")
            except Exception as e:
                log(f"[{self.tag}] 캐시 저장 실패 (무시됨): {e}")

        self._index = items

    def get_all(self):
        self._ensure_loaded()
        return list(self._index)

    def get_by_id(self, item_id: str):
        self._ensure_loaded()
        for x in self._index:
            if x.get(self.id_field) == item_id:
                return x
        return None

    def get_all_ids(self):
        self._ensure_loaded()
        return [x[self.id_field] for x in self._index if self.id_field in x]

    def retrieve_top_k(self, query: str, k: int = 3, mode: str = "embedding"):
        """
        Top-K 항목을 dict 리스트로 반환. 어댑터에서 도메인별 포매팅을 입힌다.
        mode: 'embedding' | 'keyword' | 'full'
        """
        self._ensure_loaded()
        items = self._index
        if not items:
            return []

        if mode == "full":
            return items[:k] if k < len(items) else items

        if mode == "keyword":
            return self._keyword_fallback(query, items, k)

        # embedding 모드. 가용성 없으면 keyword로 강제.
        if not embedding_available():
            log(f"[{self.tag}] 임베딩 불가 → keyword 폴백")
            return self._keyword_fallback(query, items, k)

        with_embed = [x for x in items if x.get("embedding")]
        if not with_embed:
            log(f"[{self.tag}] 캐시된 임베딩 없음 → keyword 폴백")
            return self._keyword_fallback(query, items, k)

        try:
            qvec = get_embedding(query)
        except Exception:
            qvec = None
        if qvec is None:
            log(f"[{self.tag}] 쿼리 임베딩 실패 → keyword 폴백")
            return self._keyword_fallback(query, items, k)

        scored = [(cosine_similarity(qvec, x["embedding"]), x) for x in with_embed]
        scored.sort(key=lambda t: t[0], reverse=True)
        selected = [x for _, x in scored[:k]]
        log(f"[{self.tag}] Top-{k}: {[x.get(self.id_field) for x in selected]}")
        return selected

    # ── 폴백 ─────────────────────────────────────────────────
    @staticmethod
    def _keyword_fallback(query, items, k):
        q = (query or "").lower()
        scored = []
        for x in items:
            score = sum(
                1 for kw in x.get("trigger_keywords", [])
                if kw.lower() in q
            )
            scored.append((score, x))
        scored.sort(key=lambda t: t[0], reverse=True)
        matched = [x for s, x in scored if s > 0]
        if matched:
            return matched[:k]
        return items  # 전체 폴백
