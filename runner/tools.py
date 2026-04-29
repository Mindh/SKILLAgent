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

    # ── 교육 입과 안내용 도구 (2개) ────────────────────────────────────────────

    {
        "type": "function",
        "function": {
            "name": "poster_html_generator",
            "description": "교육·행사 입과 안내용 HTML 포스터를 생성합니다. 결과는 완전한 HTML 문서이며 채팅에서 자동으로 미리보기됩니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "training_name": {"type": "string", "description": "교육명 (예: 신입사원 OJT 교육)"},
                    "session_name":  {"type": "string", "description": "차수명 (예: 2025년 1차)"},
                    "location":      {"type": "string", "description": "교육 장소 (예: 본사 3층 교육장)"},
                    "datetime":      {"type": "string", "description": "교육 일시 (예: 2025-04-15 09:00~18:00)"},
                    "instructor":    {"type": "string", "description": "강사명"},
                    "modifications": {"type": "string", "description": "수정 요청 (선택, 없으면 빈 문자열)"},
                },
                "required": ["training_name", "session_name", "location", "datetime", "instructor"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "mail_url_generator",
            "description": "메일 작성 화면을 미리 채워서 여는 mailto: URL을 생성합니다. 사용자가 클릭하면 기본 메일 클라이언트가 열립니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "메일 제목"},
                    "body":    {"type": "string", "description": "메일 본문 (평문)"},
                    "to":      {"type": "string", "description": "받는 사람 이메일 주소 (선택)"},
                },
                "required": ["subject", "body"],
            },
        },
    },

    # ── HR 운영 확장 도구 (5개) ──────────────────────────────────────────────

    {
        "type": "function",
        "function": {
            "name": "leave_balance_calculator",
            "description": "직원의 입사일과 사용한 휴가 일수를 기준으로 잔여 연차 일수를 계산합니다. employee_name으로 DB 조회하거나 join_date를 직접 지정.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_name": {"type": "string", "description": "직원 이름 (DB 조회용, 선택)"},
                    "join_date":     {"type": "string", "description": "입사일 (YYYY-MM-DD, 직접 지정용)"},
                    "used_days":     {"type": "integer", "description": "사용한 휴가 일수 (선택, 기본 0 또는 DB 값)"},
                },
                "required": [],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "expense_calculator",
            "description": "출장비 견적을 도시·교통수단·일수·직급에 따라 계산합니다. 식비·숙박비·교통비를 분리해 합산.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string", "description": "출장지 (예: 부산, 도쿄, 뉴욕)"},
                    "days":        {"type": "integer", "description": "출장 일수"},
                    "transport":   {"type": "string", "description": "교통수단 (ktx, 고속버스, 비행기_국내, 비행기_국제, 자가용)"},
                    "origin":      {"type": "string", "description": "출발지 (선택, 기본 서울)"},
                    "level":       {"type": "string", "description": "직급 (선택, 단가 보정에 사용)"},
                },
                "required": ["destination", "days"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "offboarding_checklist_generator",
            "description": "퇴사자 정보를 받아 인수인계·계정회수·자료정리·정산·작별인사 5개 카테고리 퇴사 체크리스트를 생성합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_name": {"type": "string", "description": "퇴사자 이름"},
                    "department":    {"type": "string", "description": "소속 부서"},
                    "position":      {"type": "string", "description": "직무 (선택)"},
                    "last_day":      {"type": "string", "description": "마지막 출근일 (YYYY-MM-DD)"},
                    "reason":        {"type": "string", "description": "퇴사 사유 (선택)"},
                },
                "required": ["employee_name", "department", "last_day"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "announcement_writer",
            "description": "사내 공지문(이메일·슬랙·게시판)을 주제·톤·대상에 맞춰 작성합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic":    {"type": "string", "description": "공지 주제 (예: 여름휴가 안내)"},
                    "audience": {"type": "string", "description": "대상자 (선택, 기본 전 직원)"},
                    "tone":     {"type": "string", "description": "톤 (선택: 공식적|친근한|긴급)"},
                    "key_info": {"type": "string", "description": "공지에 반드시 포함할 핵심 정보 (선택)"},
                    "channel":  {"type": "string", "description": "배포 채널 (선택: 이메일|슬랙|사내 게시판)"},
                },
                "required": ["topic"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "performance_review_template_generator",
            "description": "직급·부서·평가 종류(자기/동료/상급자/다면)에 맞춰 인사 평가 양식을 설계합니다. 섹션·가중치·문항 자동 구성.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_level":  {"type": "string", "description": "평가 대상 직급 (예: 사원, 대리, 과장, 팀장)"},
                    "department":    {"type": "string", "description": "소속 부서 (선택)"},
                    "review_type":   {"type": "string", "description": "평가 종류 (자기평가|동료평가|상급자평가|다면평가)"},
                    "review_period": {"type": "string", "description": "평가 기간 (선택, 예: 2025년 상반기)"},
                    "focus_areas":   {"type": "string", "description": "특별 강조 영역 (선택)"},
                },
                "required": ["target_level", "review_type"],
            },
        },
    },

    # ── HR 일반 지식 도구 (3개) — 일반 채팅에서 전문성 강화에 활용 ────────────

    {
        "type": "function",
        "function": {
            "name": "labor_law_qa",
            "description": "한국 노동법(근로기준법·남녀고용평등법·산업안전보건법·최저임금법 등) 관련 질문에 법령 조항 기반으로 답변합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "노동법 관련 질문"},
                    "context":  {"type": "string", "description": "추가 맥락 (선택, 예: '5인 미만 사업장')"},
                },
                "required": ["question"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "hr_etiquette",
            "description": "한국 직장 커뮤니케이션·매너에 대한 조언을 제공합니다 (메일·메신저·대면 상황별 권장 표현).",
            "parameters": {
                "type": "object",
                "properties": {
                    "situation": {"type": "string", "description": "상황 설명"},
                    "relation":  {"type": "string", "description": "상대 관계 (선택: 상급자|동료|후배|외부 거래처)"},
                    "channel":   {"type": "string", "description": "소통 채널 (선택: 대면|메신저|메일|전화)"},
                },
                "required": ["situation"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "salary_advice",
            "description": "한국 IT·서비스 업계 보상(연봉·인센티브·퇴직금) 시장 수준과 협상 조언을 제공합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic":        {"type": "string", "description": "질문 주제"},
                    "job_role":     {"type": "string", "description": "직무 (선택)"},
                    "level":        {"type": "string", "description": "직급/연차 (선택)"},
                    "company_size": {"type": "string", "description": "회사 규모 (선택: 스타트업|중견기업|대기업)"},
                    "region":       {"type": "string", "description": "지역 (선택, 기본 수도권)"},
                },
                "required": ["topic"],
            },
        },
    },
]

# ── 도구 실행 ─────────────────────────────────────────────────────────────────

_PYTHON_TOOLS = {
    "calculator", "employee_lookup", "candidate_lookup", "new_employee_lookup",
    "mail_url_generator",
    "leave_balance_calculator", "expense_calculator",
}


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
