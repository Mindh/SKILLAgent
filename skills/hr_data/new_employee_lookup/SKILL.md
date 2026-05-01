---
{
  "name": "new_employee_lookup",
  "category": "hr_data",
  "type": "python",
  "display_ko": "신규 입사자 정보 조회",
  "description": "신규 입사자 ID(N-YYYY-001 형식)로 입사 예정자 정보를 조회합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "employee_id": {
        "type": "string",
        "description": "신규 입사자 ID (예: N-2025-001)"
      }
    },
    "required": [
      "employee_id"
    ]
  }
}
---

# 신규 입사자 정보 조회

신규 입사자 ID(N-YYYY-001 형식)로 입사 예정자 정보를 조회합니다.
