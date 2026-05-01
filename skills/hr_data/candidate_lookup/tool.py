# -*- coding: utf-8 -*-
# 가상의 채용 후보자 데이터베이스
DUMMY_DB = {
    "C-001": {
        "name": "박지훈",
        "applied_position": "백엔드 개발자(시니어)",
        "status": "서류 검토",
        "score": None,
        "experience_years": 7,
        "summary": "결제·정산 백엔드 7년차. Java/Spring, MSA, Kafka 운영 경험. 핀테크 2곳 재직.",
        "email": "jihun.park@example.com",
    },
    "C-002": {
        "name": "이수민",
        "applied_position": "백엔드 개발자(주니어)",
        "status": "서류 합격",
        "score": 78,
        "experience_years": 2,
        "summary": "Java/Spring 2년차. 커머스 도메인 1곳. AWS 기본 운영 경험.",
        "email": "sumin.lee@example.com",
    },
    "C-003": {
        "name": "최가영",
        "applied_position": "프로덕트 디자이너",
        "status": "면접 예정",
        "score": 85,
        "experience_years": 4,
        "summary": "B2C 서비스 4년차 프로덕트 디자이너. Figma, 사용자 리서치 경험.",
        "email": "gayoung.choi@example.com",
    },
}


def execute(params: dict):
    cid = (params.get("candidate_id") or "").strip().upper()
    if not cid:
        return {"error": "candidate_id 파라미터가 비어 있습니다."}

    record = DUMMY_DB.get(cid)
    if not record:
        return {
            "status": "not_found",
            "message": f"후보자 ID '{cid}' 를 찾을 수 없습니다. (예: C-001, C-002, C-003)",
        }
    return {"status": "success", "candidate_id": cid, "info": record}
