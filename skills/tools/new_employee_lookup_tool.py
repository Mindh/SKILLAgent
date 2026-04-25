# -*- coding: utf-8 -*-
# 가상의 신규 입사자 데이터베이스
DUMMY_DB = {
    "N-2025-001": {
        "name": "박지훈",
        "department": "결제팀",
        "position": "백엔드 개발자",
        "level": "시니어",
        "start_date": "2025-05-01",
        "contract_type": "정규직",
        "mentor": "김철수(개발팀 과장)",
        "from_candidate_id": "C-001",
    },
    "N-2025-002": {
        "name": "이수민",
        "department": "커머스팀",
        "position": "백엔드 개발자",
        "level": "주니어",
        "start_date": "2025-05-15",
        "contract_type": "정규직(수습 3개월)",
        "mentor": "홍길동(영업팀 대리)",
        "from_candidate_id": "C-002",
    },
}


def execute(params: dict):
    eid = (params.get("employee_id") or "").strip().upper()
    if not eid:
        return {"error": "employee_id 파라미터가 비어 있습니다."}

    record = DUMMY_DB.get(eid)
    if not record:
        return {
            "status": "not_found",
            "message": f"신규 입사자 ID '{eid}' 를 찾을 수 없습니다. (예: N-2025-001)",
        }
    return {"status": "success", "employee_id": eid, "info": record}
