# -*- coding: utf-8 -*-
"""
Skill Loader — `skills/<category>/<skill_name>/` 디렉터리 구조에서
SKILL.md 프론트매터를 읽어 카탈로그·정의·실행 경로를 일괄 관리한다.

설계 원칙:
- 프론트매터는 `---` 펜스 사이의 **JSON 객체**로 작성한다 (PyYAML 의존 회피).
- 새 레이아웃이 비어 있으면 빈 카탈로그를 반환 — 호출 측이 레거시 폴백을 결정.
- 카탈로그·정의 모두 모듈 레벨에서 lazy 캐시되며 `reload()`로 강제 재빌드 가능.

Public API:
    load_all() -> Catalog
    get_definition(name) -> dict | None        # OpenAI function 형식
    get_skill(name) -> Skill | None
    list_categories() -> List[CategorySummary]
    list_skills_in_category(category) -> List[dict]
    reload()
"""
import json
import os
import re
from typing import Dict, List, Optional

from runner.utils import log

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_ROOT = os.path.join(BASE_DIR, "skills")

# 카테고리 한글 표시명 (UI·카탈로그 요약에 사용)
CATEGORY_DISPLAY_KO = {
    "hr_data": "HR 데이터 조회·계산",
    "hr_text": "HR 텍스트 분석·구조화",
    "hr_writing": "HR 문서 작성",
    "hr_eval": "HR 평가",
    "hr_knowledge": "HR 일반 지식",
    "report": "보고서·PPT 작성",
    "misc": "기타 (계산기·메일·포스터)",
}

# 카테고리 한 줄 설명 (첫 턴 요약 주입용)
CATEGORY_BLURB_KO = {
    "hr_data": "직원·후보자·신규 입사자 조회, 잔여 휴가/출장비 계산",
    "hr_text": "텍스트 번역·요약·키워드 추출, 휴가/이력서 파싱",
    "hr_writing": "JD·오퍼레터·온보딩/퇴사 체크리스트·사내 공지 작성",
    "hr_eval": "이력서-JD 적합도 평가, 인사 평가 양식 설계",
    "hr_knowledge": "한국 노동법 Q&A, 직장 매너, 연봉/보상 조언",
    "report": "보고서·PPT 기획부터 HTML 슬라이드덱 생성까지 10단계",
    "misc": "사칙연산 계산기, 메일 작성 링크 생성, 교육 포스터 HTML",
}

# 알려진 카테고리(존재하지 않으면 무시)
_KNOWN_CATEGORIES = list(CATEGORY_DISPLAY_KO.keys())


# ── 모듈 캐시 ─────────────────────────────────────────────────────────────────

_CATALOG = None  # type: Optional[dict]


class _Skill(object):
    """프론트매터 + 본문 + 실행 자산 경로를 묶은 컨테이너."""
    __slots__ = (
        "name", "category", "type", "display_ko",
        "description", "trigger_keywords",
        "parameters", "body",
        "dir_path", "tool_py_path", "prompt_md_path",
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def to_definition(self):
        """OpenAI function calling 형식으로 변환 (TOOL_DEFINITIONS 항목 형태)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description or "",
                "parameters": self.parameters or {
                    "type": "object", "properties": {}, "required": []
                },
            },
        }


# ── 프론트매터 파서 ───────────────────────────────────────────────────────────

_FRONTMATTER_RE = re.compile(
    r"^\s*---\s*\n(.*?)\n---\s*\n?(.*)$",
    re.DOTALL,
)


def _parse_frontmatter(text):
    """
    SKILL.md 본문에서 (frontmatter_dict, body_str) 반환.
    프론트매터는 `---` 펜스 사이의 JSON 객체.
    실패 시 ({}, text).
    """
    if not text:
        return {}, ""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    raw = m.group(1).strip()
    body = m.group(2)
    try:
        meta = json.loads(raw)
        if not isinstance(meta, dict):
            return {}, body
        return meta, body
    except (json.JSONDecodeError, ValueError) as e:
        log("[SkillLoader] 프론트매터 JSON 파싱 실패: {}".format(e))
        return {}, body


# ── 디렉터리 스캔 ─────────────────────────────────────────────────────────────

def _scan_skills_root():
    """
    skills/<category>/<skill_name>/SKILL.md를 모두 찾아 Skill 객체 리스트 반환.
    레거시 디렉터리(tools/, worker_prompts/, system_prompts/)는 건너뛴다.
    """
    skills = []
    if not os.path.isdir(SKILLS_ROOT):
        return skills

    legacy_dirs = {"tools", "worker_prompts", "system_prompts"}

    for cat in sorted(os.listdir(SKILLS_ROOT)):
        cat_path = os.path.join(SKILLS_ROOT, cat)
        if not os.path.isdir(cat_path):
            continue
        if cat in legacy_dirs:
            continue
        if cat.startswith("_") or cat.startswith("."):
            continue

        for skill_name in sorted(os.listdir(cat_path)):
            skill_dir = os.path.join(cat_path, skill_name)
            if not os.path.isdir(skill_dir):
                continue
            md_path = os.path.join(skill_dir, "SKILL.md")
            if not os.path.isfile(md_path):
                continue
            try:
                with open(md_path, "r", encoding="utf-8") as f:
                    text = f.read()
            except (IOError, OSError) as e:
                log("[SkillLoader] 읽기 실패 {}: {}".format(md_path, e))
                continue

            meta, body = _parse_frontmatter(text)
            if not meta:
                log("[SkillLoader] 프론트매터 없음 — 스킵: {}".format(md_path))
                continue

            tool_py = os.path.join(skill_dir, "tool.py")
            prompt_md = os.path.join(skill_dir, "prompt.md")

            skill = _Skill(
                name=meta.get("name") or skill_name,
                category=meta.get("category") or cat,
                type=meta.get("type") or ("python" if os.path.isfile(tool_py) else "llm"),
                display_ko=meta.get("display_ko") or skill_name,
                description=meta.get("description") or "",
                trigger_keywords=meta.get("trigger_keywords") or [],
                parameters=meta.get("parameters") or {
                    "type": "object", "properties": {}, "required": []
                },
                body=body.strip(),
                dir_path=skill_dir,
                tool_py_path=tool_py if os.path.isfile(tool_py) else None,
                prompt_md_path=prompt_md if os.path.isfile(prompt_md) else None,
            )
            skills.append(skill)

    return skills


def _build_catalog():
    skills = _scan_skills_root()
    by_name = {}
    by_category = {}
    for s in skills:
        if s.name in by_name:
            log("[SkillLoader] 이름 중복 감지 — 나중 항목으로 덮어씀: {}".format(s.name))
        by_name[s.name] = s
        by_category.setdefault(s.category, []).append(s)
    return {"by_name": by_name, "by_category": by_category, "all": skills}


def _ensure_loaded():
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = _build_catalog()
    return _CATALOG


# ── Public API ───────────────────────────────────────────────────────────────

def reload():
    """파일 시스템을 다시 스캔해 캐시를 무효화한다."""
    global _CATALOG
    _CATALOG = None
    _ensure_loaded()


def load_all():
    """전체 카탈로그 dict 반환 (내부 캐시 객체와 동일 참조이므로 수정 금지)."""
    return _ensure_loaded()


def all_skills():
    return list(_ensure_loaded()["all"])


def get_skill(name):
    return _ensure_loaded()["by_name"].get(name)


def get_definition(name):
    s = get_skill(name)
    return s.to_definition() if s else None


def all_definitions():
    """OpenAI 함수 형식의 모든 정의 리스트."""
    return [s.to_definition() for s in _ensure_loaded()["all"]]


def list_categories():
    """
    [{category, display_ko, blurb, count, skill_names: [...]}] 리스트 반환.
    첫 턴 요약 주입에 사용.
    """
    cat = _ensure_loaded()
    out = []
    # 알려진 카테고리 우선, 그 외(미등록)는 마지막에 알파벳 순
    seen = set()
    for c in _KNOWN_CATEGORIES:
        items = cat["by_category"].get(c, [])
        if not items:
            continue
        out.append({
            "category": c,
            "display_ko": CATEGORY_DISPLAY_KO.get(c, c),
            "blurb": CATEGORY_BLURB_KO.get(c, ""),
            "count": len(items),
            "skill_names": [s.name for s in items],
        })
        seen.add(c)
    for c in sorted(cat["by_category"].keys()):
        if c in seen:
            continue
        items = cat["by_category"][c]
        out.append({
            "category": c,
            "display_ko": c,
            "blurb": "",
            "count": len(items),
            "skill_names": [s.name for s in items],
        })
    return out


def list_skills_in_category(category):
    """
    특정 카테고리 안의 스킬들을 list_skills 메타 도구가 반환할 형태로 직렬화.
    [{name, display_ko, description, parameters}]
    """
    cat = _ensure_loaded()
    items = cat["by_category"].get(category, [])
    return [{
        "name": s.name,
        "display_ko": s.display_ko,
        "description": s.description,
        "parameters": s.parameters,
    } for s in items]


def category_summary_markdown():
    """
    첫 턴에 system prompt에 주입할 카테고리 요약 마크다운.
    각 카테고리 1줄 + 포함 스킬 이름 목록 (전체 schema는 미포함).
    """
    cats = list_categories()
    if not cats:
        return ""
    lines = ["[사용 가능한 도구 카테고리]"]
    lines.append(
        "필요한 카테고리만 펼쳐 사용하세요. "
        "특정 카테고리의 도구 상세를 보려면 "
        "`<tool_call>{\"name\":\"list_skills\",\"args\":{\"category\":\"<카테고리ID>\"}}</tool_call>`로 호출."
    )
    lines.append("")
    for c in cats:
        names = ", ".join(c["skill_names"])
        lines.append("### {} ({}, {}개)".format(c["display_ko"], c["category"], c["count"]))
        if c["blurb"]:
            lines.append(c["blurb"])
        lines.append("포함 도구: {}".format(names))
        lines.append("")
    return "\n".join(lines)


def display_name_map():
    """name → display_ko 매핑 (web.py TOOL_DISPLAY_KO 대체용)."""
    return {s.name: s.display_ko for s in _ensure_loaded()["all"]}
