# -*- coding: utf-8 -*-
import importlib.util
import json
import os

from runner.llm import call_ai
from runner.utils import cached_file

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── OpenAI function calling 형식 도구 정의 ───────────────────────────────────

TOOL_DEFINITIONS = [

    # ── Python 함수 기반 (4개) ────────────────────────────────────────────────

    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "두 수의 사칙연산(더하기, 빼기, 곱하기, 나누기)을 계산합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "num1":     {"type": "number", "description": "첫 번째 숫자"},
                    "num2":     {"type": "number", "description": "두 번째 숫자"},
                    "operator": {"type": "string",  "enum": ["+", "-", "*", "/"], "description": "연산자"},
                },
                "required": ["num1", "num2", "operator"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "employee_lookup",
            "description": "직원 이름으로 사내 인사 정보(부서, 직급, 잔여 휴가일, 연락처 등)를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_name": {"type": "string", "description": "조회할 직원의 이름 (예: 홍길동)"},
                },
                "required": ["employee_name"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "candidate_lookup",
            "description": "채용 후보자 ID(C-001 형식)로 지원자 정보를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string", "description": "후보자 ID (예: C-001, C-002)"},
                },
                "required": ["candidate_id"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "new_employee_lookup",
            "description": "신규 입사자 ID(N-YYYY-001 형식)로 입사 예정자 정보를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {"type": "string", "description": "신규 입사자 ID (예: N-2025-001)"},
                },
                "required": ["employee_id"],
            },
        },
    },

    # ── LLM 생성 기반 (9개) ───────────────────────────────────────────────────

    {
        "type": "function",
        "function": {
            "name": "translate",
            "description": "텍스트를 지정한 언어로 번역합니다. 한국어, 영어, 일본어, 중국어 등을 지원합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text":        {"type": "string", "description": "번역할 원문 텍스트"},
                    "target_lang": {"type": "string", "description": "목표 언어 (예: Korean, English, Japanese). 기본값: English"},
                },
                "required": ["text"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "summarize",
            "description": "긴 텍스트를 원문의 30% 이내 분량으로 핵심만 요약합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "요약할 원문 텍스트"},
                },
                "required": ["text"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "extract",
            "description": "텍스트에서 핵심 키워드나 항목을 최대 5개 추출합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "분석할 원문 텍스트"},
                },
                "required": ["text"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "vacation_parser",
            "description": "휴가 신청 텍스트에서 직원 이름, 시작일, 종료일, 사유를 구조화하여 추출합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "휴가 신청 내용이 담긴 텍스트"},
                },
                "required": ["text"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "jd_generator",
            "description": "직무 정보를 입력받아 한국 기업 표준 형식의 채용 공고(JD) 마크다운 초안을 생성합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_title":    {"type": "string", "description": "직무명 (예: 백엔드 개발자, HR 매니저)"},
                    "level":        {"type": "string", "description": "직급 또는 연차 (예: 시니어, 3~5년차)"},
                    "headcount":    {"type": "integer", "description": "채용 인원 수"},
                    "must_have":    {"type": "array", "items": {"type": "string"}, "description": "필수 자격/경험 목록"},
                    "nice_to_have": {"type": "array", "items": {"type": "string"}, "description": "우대 자격 목록"},
                    "domain":       {"type": "string", "description": "도메인 또는 팀 (예: 결제, 커머스, HR)"},
                    "employment_type": {"type": "string", "description": "근무 형태 (예: 정규직, 계약직)"},
                },
                "required": ["job_title"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "resume_parser",
            "description": "자유 형식의 이력서 텍스트를 학력·경력·기술 스택 등 구조화된 형태로 변환합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resume_text": {"type": "string", "description": "분석할 이력서 원문 텍스트"},
                },
                "required": ["resume_text"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "jd_resume_match_score",
            "description": "채용 공고(JD)와 이력서를 비교하여 0~100 매칭 점수와 추천 여부, 강점/약점을 평가합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "jd_text":     {"type": "string", "description": "채용 공고(JD) 텍스트"},
                    "resume_text": {"type": "string", "description": "지원자 이력서 텍스트"},
                },
                "required": ["jd_text", "resume_text"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "offer_letter_drafter",
            "description": "합격자 정보를 입력받아 공식 오퍼레터(처우 제안서) 초안을 한국어로 작성합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_name": {"type": "string", "description": "합격자 이름"},
                    "position":       {"type": "string", "description": "직무명"},
                    "level":          {"type": "string", "description": "직급"},
                    "annual_salary":  {"type": "integer", "description": "연봉 (단위: 만원)"},
                    "start_date":     {"type": "string", "description": "입사 예정일 (예: 2025-03-01)"},
                    "department":     {"type": "string", "description": "배치 부서"},
                },
                "required": ["candidate_name", "position"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "onboarding_checklist_generator",
            "description": "신규 입사자 정보를 받아 서류·계정·교육·미팅·문서권한 5개 카테고리의 입사 1주차 체크리스트를 생성합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_name": {"type": "string", "description": "입사자 이름"},
                    "position":      {"type": "string", "description": "직무"},
                    "level":         {"type": "string", "description": "직급"},
                    "department":    {"type": "string", "description": "배치 부서"},
                    "start_date":    {"type": "string", "description": "입사일"},
                },
                "required": ["employee_name"],
            },
        },
    },
]

# ── 도구 실행 ─────────────────────────────────────────────────────────────────

_PYTHON_TOOLS = {"calculator", "employee_lookup", "candidate_lookup", "new_employee_lookup"}


def execute_tool(name: str, args: dict):
    """도구 이름과 인자를 받아 실행하고 결과를 반환한다."""
    if name in _PYTHON_TOOLS:
        return _execute_python_tool(name, args)
    else:
        return _execute_llm_tool(name, args)


def _execute_python_tool(name: str, args: dict):
    tool_path = os.path.join(BASE_DIR, "skills", "tools", f"{name}_tool.py")
    spec = importlib.util.spec_from_file_location(f"tool_{name}", tool_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.execute(args)


def _execute_llm_tool(name: str, args: dict):
    skill_prompt = cached_file(f"skills/worker_prompts/{name}_skill.md")
    user_input = json.dumps(args, ensure_ascii=False)
    return call_ai(skill_prompt, user_input)


def get_tool_descriptions() -> str:
    """시스템 프롬프트에 삽입할 도구 목록 마크다운을 생성한다."""
    lines = []
    for item in TOOL_DEFINITIONS:
        fn = item["function"]
        name = fn["name"]
        desc = fn["description"]
        props = fn["parameters"].get("properties", {})
        required = fn["parameters"].get("required", [])

        lines.append(f"### {name}")
        lines.append(desc)
        if props:
            lines.append("파라미터:")
            for k, v in props.items():
                req = " (필수)" if k in required else " (선택)"
                param_desc = v.get("description", "")
                enum_vals = v.get("enum")
                if enum_vals:
                    param_desc += f" [{', '.join(str(e) for e in enum_vals)}]"
                lines.append(f"  - {k}{req}: {param_desc}")
        lines.append("")

    return "\n".join(lines)
