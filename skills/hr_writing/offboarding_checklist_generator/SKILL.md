---
{
  "name": "offboarding_checklist_generator",
  "category": "hr_writing",
  "type": "llm",
  "display_ko": "퇴사 체크리스트 생성",
  "description": "퇴사자 정보를 받아 인수인계·계정회수·자료정리·정산·작별인사 5개 카테고리 퇴사 체크리스트를 생성합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "employee_name": {
        "type": "string",
        "description": "퇴사자 이름"
      },
      "department": {
        "type": "string",
        "description": "소속 부서"
      },
      "position": {
        "type": "string",
        "description": "직무 (선택)"
      },
      "last_day": {
        "type": "string",
        "description": "마지막 출근일 (YYYY-MM-DD)"
      },
      "reason": {
        "type": "string",
        "description": "퇴사 사유 (선택)"
      }
    },
    "required": [
      "employee_name",
      "department",
      "last_day"
    ]
  }
}
---

# 퇴사 체크리스트 생성

퇴사자 정보를 받아 인수인계·계정회수·자료정리·정산·작별인사 5개 카테고리 퇴사 체크리스트를 생성합니다.
