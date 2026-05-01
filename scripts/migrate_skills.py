# -*- coding: utf-8 -*-
"""
1회용 마이그레이션 스크립트:
  skills/tools/<name>_tool.py
  skills/worker_prompts/<name>_skill.md
  →
  skills/<category>/<name>/SKILL.md (프론트매터)
  skills/<category>/<name>/tool.py 또는 prompt.md

실행:
    python scripts/migrate_skills.py            # 실제 이동
    python scripts/migrate_skills.py --dry-run  # 계획만 출력

기존 파일은 git mv 대신 일반 shutil.move를 쓰므로 git에서 변경 추적은
add/commit 시점에 이뤄진다.
"""
from __future__ import print_function
import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from runner.tools import TOOL_DEFINITIONS, _PYTHON_TOOLS  # noqa: E402

# ── 카테고리 매핑 (33개 도구) ───────────────────────────────────────────────
CATEGORY_MAP = {
    # hr_data
    "employee_lookup": "hr_data",
    "candidate_lookup": "hr_data",
    "new_employee_lookup": "hr_data",
    "leave_balance_calculator": "hr_data",
    "expense_calculator": "hr_data",
    # hr_text
    "translate": "hr_text",
    "summarize": "hr_text",
    "extract": "hr_text",
    "vacation_parser": "hr_text",
    "resume_parser": "hr_text",
    # hr_writing
    "jd_generator": "hr_writing",
    "offer_letter_drafter": "hr_writing",
    "onboarding_checklist_generator": "hr_writing",
    "offboarding_checklist_generator": "hr_writing",
    "announcement_writer": "hr_writing",
    # hr_eval
    "jd_resume_match_score": "hr_eval",
    "performance_review_template_generator": "hr_eval",
    # hr_knowledge
    "labor_law_qa": "hr_knowledge",
    "hr_etiquette": "hr_knowledge",
    "salary_advice": "hr_knowledge",
    # report
    "report_brief_analyzer": "report",
    "background_research": "report",
    "audience_analyzer": "report",
    "key_message_extractor": "report",
    "storytelling_arc": "report",
    "report_outline_generator": "report",
    "slide_content_enricher": "report",
    "data_visualization_recommender": "report",
    "html_slide_deck_generator": "report",
    "speaker_notes_generator": "report",
    # misc
    "calculator": "misc",
    "mail_url_generator": "misc",
    "poster_html_generator": "misc",
}

# ── 한글 표시명 (web.py TOOL_DISPLAY_KO 동기화) ────────────────────────────
DISPLAY_KO = {
    "calculator": "계산기",
    "employee_lookup": "직원 정보 조회",
    "candidate_lookup": "후보자 정보 조회",
    "new_employee_lookup": "신규 입사자 정보 조회",
    "translate": "번역",
    "summarize": "요약",
    "extract": "키워드 추출",
    "vacation_parser": "휴가 정보 추출",
    "jd_generator": "채용공고 생성",
    "resume_parser": "이력서 분석",
    "jd_resume_match_score": "이력서 적합도 평가",
    "offer_letter_drafter": "오퍼레터 작성",
    "onboarding_checklist_generator": "온보딩 체크리스트 생성",
    "poster_html_generator": "교육 포스터 생성",
    "mail_url_generator": "메일 작성 링크 생성",
    "leave_balance_calculator": "잔여 휴가 계산",
    "expense_calculator": "출장비 견적",
    "offboarding_checklist_generator": "퇴사 체크리스트 생성",
    "announcement_writer": "사내 공지문 작성",
    "performance_review_template_generator": "평가 양식 생성",
    "labor_law_qa": "노동법 Q&A",
    "hr_etiquette": "직장 매너 조언",
    "salary_advice": "연봉/보상 조언",
    "report_brief_analyzer": "보고서 의도 분석",
    "background_research": "배경·맥락 조사",
    "audience_analyzer": "청중 분석",
    "key_message_extractor": "핵심 메시지 추출",
    "storytelling_arc": "스토리 흐름 설계",
    "report_outline_generator": "보고서 개요 생성",
    "slide_content_enricher": "슬라이드 본문 보강",
    "data_visualization_recommender": "데이터 시각화 추천",
    "html_slide_deck_generator": "HTML 슬라이드덱 생성",
    "speaker_notes_generator": "발표 스크립트 작성",
}

# ── 트리거 키워드 (간단한 휴리스틱 — 워크플로우 매칭에 활용 가능) ──────────
# 빈 리스트로 두면 키워드 매칭 X. 일부 자주 쓰이는 도구만 채움.
TRIGGER_KEYWORDS = {
    "translate": ["번역", "translate", "영어로", "한국어로"],
    "summarize": ["요약", "줄여", "핵심만"],
    "extract": ["키워드", "추출", "뽑아"],
    "calculator": ["계산", "더하", "빼", "곱하", "나누"],
    "employee_lookup": ["직원", "사번 조회"],
    "leave_balance_calculator": ["잔여 휴가", "연차 잔여", "남은 휴가"],
    "expense_calculator": ["출장비", "견적", "출장 경비"],
}


def _get_def(name):
    for d in TOOL_DEFINITIONS:
        if d["function"]["name"] == name:
            return d
    return None


def _build_skill_md(name, definition, category, tool_type):
    fn = definition["function"]
    front = {
        "name": name,
        "category": category,
        "type": tool_type,
        "display_ko": DISPLAY_KO.get(name, name),
        "description": fn.get("description", ""),
        "trigger_keywords": TRIGGER_KEYWORDS.get(name, []),
        "parameters": fn.get("parameters", {
            "type": "object", "properties": {}, "required": []
        }),
    }
    front_json = json.dumps(front, ensure_ascii=False, indent=2)
    body = "# {display}\n\n{desc}\n".format(
        display=DISPLAY_KO.get(name, name),
        desc=fn.get("description", ""),
    )
    return "---\n{}\n---\n\n{}".format(front_json, body)


def plan():
    """이동 계획을 생성. (action, src, dst, write_file_content) 튜플 리스트."""
    plans = []
    skills_root = os.path.join(ROOT, "skills")

    for name, category in CATEGORY_MAP.items():
        defn = _get_def(name)
        if defn is None:
            print("[!] TOOL_DEFINITIONS에 없는 도구: {}".format(name))
            continue
        is_python = name in _PYTHON_TOOLS
        tool_type = "python" if is_python else "llm"
        skill_dir = os.path.join(skills_root, category, name)

        # SKILL.md
        plans.append((
            "write",
            None,
            os.path.join(skill_dir, "SKILL.md"),
            _build_skill_md(name, defn, category, tool_type),
        ))

        # tool.py 또는 prompt.md 이동
        if is_python:
            src = os.path.join(skills_root, "tools", "{}_tool.py".format(name))
            dst = os.path.join(skill_dir, "tool.py")
            if os.path.isfile(src):
                plans.append(("move", src, dst, None))
            else:
                print("[!] Python 도구 원본 없음: {}".format(src))
        else:
            src = os.path.join(skills_root, "worker_prompts", "{}_skill.md".format(name))
            dst = os.path.join(skill_dir, "prompt.md")
            if os.path.isfile(src):
                plans.append(("move", src, dst, None))
            else:
                print("[!] LLM 프롬프트 원본 없음: {}".format(src))

    return plans


def execute(plans, dry_run):
    for action, src, dst, content in plans:
        rel_dst = os.path.relpath(dst, ROOT)
        if action == "write":
            print("  [WRITE] {}".format(rel_dst))
            if not dry_run:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "w", encoding="utf-8") as f:
                    f.write(content)
        elif action == "move":
            rel_src = os.path.relpath(src, ROOT)
            print("  [MOVE]  {} -> {}".format(rel_src, rel_dst))
            if not dry_run:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, dst)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="실제 이동 없이 계획만 출력")
    args = parser.parse_args()

    plans = plan()
    print()
    print("=" * 60)
    print("총 {}건의 작업 계획 (33개 도구 × WRITE+MOVE)".format(len(plans)))
    print("dry-run: {}".format(args.dry_run))
    print("=" * 60)
    execute(plans, dry_run=args.dry_run)
    print()
    print("done. (legacy dirs skills/tools, skills/worker_prompts may be empty - manual cleanup recommended)")


if __name__ == "__main__":
    main()
