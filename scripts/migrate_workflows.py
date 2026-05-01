# -*- coding: utf-8 -*-
"""
Phase 3 마이그레이션:
  agents/definitions/<workflow_id>.md 파일 11개의 맨 앞에
  JSON 프론트매터(--- ... ---)를 삽입한다.

이미 프론트매터가 있는 파일은 건너뛴다 (멱등).

실행:
    python scripts/migrate_workflows.py             # 실제 변경
    python scripts/migrate_workflows.py --dry-run   # 계획만 출력
"""
from __future__ import print_function
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFS_DIR = os.path.join(ROOT, "agents", "definitions")

# ── 워크플로우별 메타데이터 ───────────────────────────────────────────────
# - display_ko: UI/요약에 노출되는 한글명
# - categories: 서브에이전트 시작 시 즉시 펼쳐질 도구 카테고리들 (다른 카테고리는 list_skills로 펼침)
# - max_turns: 서브에이전트의 최대 ReAct 사이클 수 (안전장치)
# - mode: "dialog" — 다턴 대화형. 사용자 입력을 계속 받음. 종료는 <workflow_complete> 태그로.
WORKFLOWS = {
    "leave_intake": {
        "display_ko": "휴직 접수",
        "categories": ["hr_data"],
        "max_turns": 15,
        "mode": "dialog",
    },
    "vacation_request": {
        "display_ko": "연차/휴가 신청",
        "categories": ["hr_data", "hr_text"],
        "max_turns": 12,
        "mode": "dialog",
    },
    "offboarding_intake": {
        "display_ko": "퇴사 접수",
        "categories": ["hr_data", "hr_writing"],
        "max_turns": 15,
        "mode": "dialog",
    },
    "recruitment_intake": {
        "display_ko": "채용 요청 접수",
        "categories": ["hr_data", "hr_text", "hr_writing", "hr_eval"],
        "max_turns": 20,
        "mode": "dialog",
    },
    "onboarding_intake": {
        "display_ko": "온보딩 접수",
        "categories": ["hr_data", "hr_writing"],
        "max_turns": 15,
        "mode": "dialog",
    },
    "job_description_writing": {
        "display_ko": "직무기술서 작성",
        "categories": ["hr_writing"],
        "max_turns": 12,
        "mode": "dialog",
    },
    "business_trip_request": {
        "display_ko": "출장 신청",
        "categories": ["hr_data", "misc"],
        "max_turns": 12,
        "mode": "dialog",
    },
    "performance_review": {
        "display_ko": "인사 평가 진행",
        "categories": ["hr_data", "hr_eval"],
        "max_turns": 15,
        "mode": "dialog",
    },
    "health_checkup_intake": {
        "display_ko": "건강검진 안내",
        "categories": ["hr_data", "hr_writing", "misc"],
        "max_turns": 12,
        "mode": "dialog",
    },
    "training_admission_intake": {
        "display_ko": "교육 입과 안내",
        "categories": ["misc", "hr_writing"],
        "max_turns": 12,
        "mode": "dialog",
    },
    "report_writing": {
        "display_ko": "보고서·PPT 작성",
        "categories": ["report"],
        "max_turns": 25,
        "mode": "dialog",
    },
}


# 이미 프론트매터가 있는지 검사
_FM_RE = re.compile(r"^\s*---\s*\n.*?\n---\s*\n", re.DOTALL)


def _build_frontmatter(wf_id, meta):
    front = {
        "id": wf_id,
        "display_ko": meta["display_ko"],
        "categories": meta["categories"],
        "max_turns": meta["max_turns"],
        "mode": meta["mode"],
    }
    return "---\n{}\n---\n\n".format(
        json.dumps(front, ensure_ascii=False, indent=2)
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for wf_id, meta in WORKFLOWS.items():
        path = os.path.join(DEFS_DIR, "{}.md".format(wf_id))
        rel = os.path.relpath(path, ROOT)
        if not os.path.isfile(path):
            print("[!] 파일 없음: {}".format(rel))
            continue
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if _FM_RE.match(text):
            print("[skip] 이미 프론트매터 있음: {}".format(rel))
            continue
        new_text = _build_frontmatter(wf_id, meta) + text
        if args.dry_run:
            print("[dry] would insert frontmatter into {}".format(rel))
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_text)
            print("[done] {}".format(rel))


if __name__ == "__main__":
    main()
