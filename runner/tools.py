# -*- coding: utf-8 -*-
"""
Tools 디스패처.

Phase 2 변경:
- TOOL_DEFINITIONS는 더 이상 하드코딩되지 않고 `runner.skill_loader`에서
  SKILL.md 프론트매터를 읽어 동적으로 구성된다.
- Python 도구는 `skills/<category>/<name>/tool.py`에서 importlib로 로드.
- LLM 도구는 `skills/<category>/<name>/prompt.md`를 system_prompt로 call_ai 호출.
- `validate_args(name, args)`로 필수 파라미터 검증.
- `get_tool_descriptions()`는 그대로 동작하지만 보통 첫 턴에는 호출되지 않고,
  Phase 2부터는 `skill_loader.category_summary_markdown()`이 사용된다.
- `list_skills` 메타 도구를 등록 — 모델이 카테고리 안의 도구 상세를 펼쳐볼 수 있다.
"""
import importlib.util
import json
import os

from runner import skill_loader
from runner.llm import call_ai

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── 메타 도구: list_skills ───────────────────────────────────────────────────
# 진보적 노출(progressive disclosure)을 위해 카테고리 안의 도구 상세를 모델이
# 직접 요청할 수 있도록 한다.
META_TOOL_LIST_SKILLS = {
    "type": "function",
    "function": {
        "name": "list_skills",
        "description": (
            "특정 카테고리에 속한 도구들의 이름·설명·파라미터 상세를 반환합니다. "
            "처음 보는 카테고리의 도구를 호출하기 전에 한 번 펼쳐 확인하세요."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "카테고리 ID (예: hr_data, hr_text, hr_writing, hr_eval, hr_knowledge, report, misc)",
                },
            },
            "required": ["category"],
        },
    },
}

_META_TOOL_NAMES = {"list_skills"}


# ── 동적 TOOL_DEFINITIONS ────────────────────────────────────────────────────

def _build_tool_definitions():
    """skill_loader의 모든 정의 + 메타 도구를 합쳐 반환."""
    defs = list(skill_loader.all_definitions())
    defs.append(META_TOOL_LIST_SKILLS)
    return defs


# 모듈 로드 시 1회 빌드. skill_loader.reload() 후엔 reload_tools()로 재빌드.
TOOL_DEFINITIONS = _build_tool_definitions()
_TOOL_INDEX = None


def reload_tools():
    """파일 변경 후 카탈로그·정의 캐시를 강제로 다시 빌드."""
    global TOOL_DEFINITIONS, _TOOL_INDEX
    skill_loader.reload()
    TOOL_DEFINITIONS = _build_tool_definitions()
    _TOOL_INDEX = None


def _build_tool_index():
    global _TOOL_INDEX
    _TOOL_INDEX = {d["function"]["name"]: d for d in TOOL_DEFINITIONS}


def get_tool_definition(name):
    """도구 이름으로 정의 dict 반환. 없으면 None."""
    if _TOOL_INDEX is None:
        _build_tool_index()
    return _TOOL_INDEX.get(name)


def validate_args(name, args):
    """
    도구 호출 인자를 가볍게 검증한다.

    반환: (ok: bool, error_msg: str)
      - 미등록 도구이거나 args가 dict가 아니면 실패
      - 필수 파라미터가 누락되거나 None/빈 문자열이면 실패
      - 타입 불일치는 경고만 — 모델이 string으로 number를 보내는 경우가 흔하므로 차단하지 않음
    """
    spec = get_tool_definition(name)
    if spec is None:
        return False, "알 수 없는 도구: '{}'. 등록된 도구만 사용하세요.".format(name)
    if not isinstance(args, dict):
        return False, "args는 객체(JSON dict)여야 합니다 (받은 타입: {})".format(
            type(args).__name__
        )
    params = spec["function"].get("parameters", {})
    required = params.get("required", []) or []
    missing = []
    for k in required:
        if k not in args:
            missing.append(k)
        else:
            v = args[k]
            if v is None or (isinstance(v, str) and not v.strip()):
                missing.append(k)
    if missing:
        return False, "필수 파라미터 누락 또는 비어 있음: {}".format(", ".join(missing))
    return True, ""


# ── 도구 실행 ─────────────────────────────────────────────────────────────────

def execute_tool(name, args):
    """도구 이름과 인자를 받아 실행하고 결과를 반환한다."""
    if name in _META_TOOL_NAMES:
        return _execute_meta_tool(name, args)

    skill = skill_loader.get_skill(name)
    if skill is None:
        raise KeyError("등록되지 않은 도구: {}".format(name))

    if skill.type == "python":
        return _execute_python_skill(skill, args)
    return _execute_llm_skill(skill, args)


def _execute_meta_tool(name, args):
    if name == "list_skills":
        category = (args or {}).get("category", "").strip()
        if not category:
            return {"error": "category 파라미터 필요"}
        items = skill_loader.list_skills_in_category(category)
        if not items:
            valid = [c["category"] for c in skill_loader.list_categories()]
            return {
                "error": "알 수 없는 카테고리: {}".format(category),
                "valid_categories": valid,
            }
        return {"category": category, "skills": items}
    return {"error": "알 수 없는 메타 도구: {}".format(name)}


def _execute_python_skill(skill, args):
    if not skill.tool_py_path or not os.path.isfile(skill.tool_py_path):
        raise FileNotFoundError(
            "Python 도구 파일 없음: {} (예상 경로: {})".format(skill.name, skill.tool_py_path)
        )
    spec = importlib.util.spec_from_file_location("tool_{}".format(skill.name), skill.tool_py_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.execute(args)


def _execute_llm_skill(skill, args):
    if not skill.prompt_md_path or not os.path.isfile(skill.prompt_md_path):
        raise FileNotFoundError(
            "LLM 프롬프트 파일 없음: {} (예상 경로: {})".format(skill.name, skill.prompt_md_path)
        )
    with open(skill.prompt_md_path, "r", encoding="utf-8") as f:
        skill_prompt = f.read()
    user_input = json.dumps(args, ensure_ascii=False)
    return call_ai(skill_prompt, user_input)


# ── 설명 생성 (호환용·디버그용) ──────────────────────────────────────────────

def get_tool_descriptions():
    """
    시스템 프롬프트에 삽입할 **전체** 도구 목록 마크다운.
    Phase 2부터 첫 턴 주입에는 보통 사용되지 않고
    `skill_loader.category_summary_markdown()`이 대신 쓰인다.
    디버그/관리 화면용으로 유지.
    """
    lines = []
    for item in TOOL_DEFINITIONS:
        fn = item["function"]
        name = fn["name"]
        desc = fn["description"]
        props = fn["parameters"].get("properties", {})
        required = fn["parameters"].get("required", [])

        lines.append("### {}".format(name))
        lines.append(desc)
        if props:
            lines.append("파라미터:")
            for k, v in props.items():
                req = " (필수)" if k in required else " (선택)"
                param_desc = v.get("description", "")
                enum_vals = v.get("enum")
                if enum_vals:
                    param_desc += " [{}]".format(", ".join(str(e) for e in enum_vals))
                lines.append("  - {}{}: {}".format(k, req, param_desc))
        lines.append("")

    return "\n".join(lines)
