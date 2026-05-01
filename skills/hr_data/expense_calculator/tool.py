# -*- coding: utf-8 -*-
"""
출장비 견적 계산기.

도시·교통수단·등급별 단가표를 기반으로 출장 예산을 산출.
"""

# 도시별 일일 식비/숙박비 (단위: 원)
_CITY_RATES = {
    "서울":   {"meal": 30000, "lodging": 90000},
    "부산":   {"meal": 25000, "lodging": 80000},
    "대구":   {"meal": 25000, "lodging": 70000},
    "광주":   {"meal": 25000, "lodging": 70000},
    "대전":   {"meal": 25000, "lodging": 70000},
    "제주":   {"meal": 30000, "lodging": 100000},
    "도쿄":   {"meal": 50000, "lodging": 150000},
    "오사카": {"meal": 45000, "lodging": 130000},
    "베이징": {"meal": 35000, "lodging": 110000},
    "상하이": {"meal": 40000, "lodging": 120000},
    "뉴욕":   {"meal": 80000, "lodging": 250000},
    "샌프란시스코": {"meal": 80000, "lodging": 280000},
}

# 교통수단별 편도 운임 추정 (단위: 원)
_TRANSPORT_RATES = {
    "ktx":      {"서울-부산": 60000, "서울-대구": 45000, "서울-광주": 50000,
                 "서울-대전": 25000, "default": 50000},
    "고속버스": {"default": 30000},
    "비행기_국내": {"default": 80000},
    "비행기_국제": {"제주": 200000, "도쿄": 350000, "오사카": 400000,
                    "베이징": 500000, "상하이": 600000,
                    "뉴욕": 1500000, "샌프란시스코": 1300000,
                    "default": 600000},
    "자가용":   {"default": 0},  # 별도 마일리지
}

# 직급별 등급 (등급 높을수록 한도 ↑)
_LEVEL_MULTIPLIER = {
    "사원": 1.0, "주임": 1.0, "대리": 1.1,
    "과장": 1.2, "차장": 1.3, "부장": 1.5,
    "이사": 1.8, "임원": 2.0,
}


def execute(params: dict):
    """
    params:
      - destination: 출장지 (예: "부산", "도쿄")
      - days:        출장 일수 (정수, 필수)
      - transport:   교통수단 (ktx | 고속버스 | 비행기_국내 | 비행기_국제 | 자가용)
      - origin:      출발지 (선택, 기본 "서울")
      - level:       직급 (선택, 단가 보정)

    반환:
      {"status": "success", "breakdown": {...}, "total": int, "summary": str}
    """
    destination = (params.get("destination") or "").strip()
    days = params.get("days")
    transport = (params.get("transport") or "ktx").strip().lower()
    origin = (params.get("origin") or "서울").strip()
    level = (params.get("level") or "").strip()

    if not destination:
        return {"status": "error", "message": "destination(출장지)이 필요합니다."}
    try:
        days = int(days)
    except (TypeError, ValueError):
        return {"status": "error", "message": "days(출장 일수, 정수)가 필요합니다."}
    if days <= 0:
        return {"status": "error", "message": "days는 1 이상이어야 합니다."}

    # 도시 단가 조회 (없으면 서울 단가 사용 + 미등록 알림)
    rates = _CITY_RATES.get(destination)
    city_note = ""
    if not rates:
        rates = _CITY_RATES["서울"]
        city_note = f"(미등록 도시이므로 서울 기준 단가 적용)"

    meal_total = rates["meal"] * days
    lodging_total = rates["lodging"] * max(days - 1, 0)  # 마지막 날 숙박 X

    # 교통비
    transport_table = _TRANSPORT_RATES.get(transport, _TRANSPORT_RATES["ktx"])
    if transport in ("ktx", "비행기_국제"):
        route_key = f"{origin}-{destination}" if transport == "ktx" else destination
        transport_one_way = transport_table.get(route_key, transport_table["default"])
    else:
        transport_one_way = transport_table["default"]
    transport_total = transport_one_way * 2  # 왕복

    # 직급 보정
    multiplier = _LEVEL_MULTIPLIER.get(level, 1.0)
    subtotal = meal_total + lodging_total + transport_total
    total = int(subtotal * multiplier)

    summary = (
        f"{destination} {days}일 출장 견적: 약 {total:,}원 "
        f"(교통 {transport_total:,} + 숙박 {lodging_total:,} + 식비 {meal_total:,}"
        f"{', 직급 ' + level + ' 보정 x' + str(multiplier) if level else ''})"
    )
    if city_note:
        summary += " " + city_note

    return {
        "status": "success",
        "destination": destination,
        "days": days,
        "transport": transport,
        "level": level or "(기본)",
        "breakdown": {
            "meal": meal_total,
            "lodging": lodging_total,
            "transport": transport_total,
            "level_multiplier": multiplier,
        },
        "total": total,
        "summary": summary,
    }
