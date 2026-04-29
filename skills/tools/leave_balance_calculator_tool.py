# -*- coding: utf-8 -*-
"""
직원 잔여 휴가 계산기.

연차 부여 규칙(한국 근로기준법 단순화):
- 입사 1년 미만: 매월 1일씩 발생 (최대 11일)
- 입사 1년 이상 ~ 3년 미만: 15일/년
- 입사 3년 이상부터 2년마다 1일 추가 (최대 25일)

기본 데이터는 employee_lookup_tool.py와 같은 DUMMY_DB를 참조하나,
파라미터로 직접 입사일을 받을 수도 있다.
"""
from datetime import date


# 가상 사내 데이터 (employee_lookup과 일치하는 인물 + 추가)
_LEAVE_DB = {
    "홍길동": {"join_date": "2018-03-01", "used_days": 8},
    "김철수": {"join_date": "2020-07-15", "used_days": 10},
    "이영희": {"join_date": "2024-01-02", "used_days": 2},
    "박민수": {"join_date": "2015-04-20", "used_days": 5},
    "최지은": {"join_date": "2023-09-01", "used_days": 0},
}


def _calc_total_days(join_date_str: str, today: date = None) -> int:
    """입사일과 오늘 날짜로 부여 연차일 수 계산 (간소화 모델)."""
    if today is None:
        today = date.today()
    try:
        y, m, d = map(int, join_date_str.split("-"))
        join = date(y, m, d)
    except (ValueError, AttributeError):
        return 0

    months = (today.year - join.year) * 12 + (today.month - join.month)
    years = months // 12

    if years < 1:
        # 1년 미만: 매월 1일, 최대 11일
        return min(months, 11)
    if years < 3:
        return 15
    # 3년 이상: 15 + (year - 1) // 2 — 2년마다 1일, 상한 25일
    extra = (years - 1) // 2
    return min(15 + extra, 25)


def execute(params: dict):
    """
    params:
      - employee_name: 직원 이름 (필수, DB에서 조회)
      또는
      - join_date:     입사일 (YYYY-MM-DD, 직접 지정)
      - used_days:     사용한 휴가 일수 (직접 지정, 기본 0)

    반환:
      성공 시: {"status":"success", "employee_name", "join_date",
                "total_days", "used_days", "remaining_days"}
      실패 시: {"status":"not_found"|"error", "message"}
    """
    name = (params.get("employee_name") or "").strip()
    join_date_str = (params.get("join_date") or "").strip()
    used_days = params.get("used_days")

    # 직원명으로 DB 조회
    if name:
        record = _LEAVE_DB.get(name)
        if not record:
            return {
                "status": "not_found",
                "message": f"'{name}' 직원의 휴가 기록을 찾을 수 없습니다.",
            }
        join_date_str = record["join_date"]
        if used_days is None:
            used_days = record["used_days"]

    if not join_date_str:
        return {
            "status": "error",
            "message": "employee_name 또는 join_date 중 하나는 필요합니다.",
        }

    try:
        used_days = int(used_days) if used_days is not None else 0
    except (TypeError, ValueError):
        used_days = 0

    total = _calc_total_days(join_date_str)
    remaining = max(total - used_days, 0)

    return {
        "status": "success",
        "employee_name": name or "(직접지정)",
        "join_date": join_date_str,
        "total_days": total,
        "used_days": used_days,
        "remaining_days": remaining,
    }
