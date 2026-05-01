# 가상의 사내 인사 데이터베이스 매핑
DUMMY_DB = {
    "홍길동": {"department": "영업팀", "position": "대리", "remaining_vacation": 12, "phone": "010-1234-5678"},
    "김철수": {"department": "개발팀", "position": "과장", "remaining_vacation": 5, "phone": "010-9876-5432"},
    "이영희": {"department": "인사팀", "position": "사원", "remaining_vacation": 15, "phone": "010-1111-2222"}
}

def execute(params: dict):
    name = params.get("employee_name", "").strip()
    
    if not name:
        return {"error": "직원 이름 파라미터가 비어 있습니다."}
        
    record = DUMMY_DB.get(name)
    if record:
        return {
            "status": "success",
            "name": name,
            "info": record
        }
    else:
        return {
            "status": "not_found",
            "message": f"데이터베이스에서 '{name}' 직원을 찾을 수 없습니다."
        }
