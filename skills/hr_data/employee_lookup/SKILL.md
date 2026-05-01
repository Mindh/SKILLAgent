---
{
  "name": "employee_lookup",
  "category": "hr_data",
  "type": "python",
  "display_ko": "직원 정보 조회",
  "description": "직원 이름으로 사내 인사 정보(부서, 직급, 잔여 휴가일, 연락처 등)를 조회합니다.",
  "trigger_keywords": [
    "직원",
    "사번 조회"
  ],
  "parameters": {
    "type": "object",
    "properties": {
      "employee_name": {
        "type": "string",
        "description": "조회할 직원의 이름 (예: 홍길동)"
      }
    },
    "required": [
      "employee_name"
    ]
  }
}
---

# 직원 정보 조회

직원 이름으로 사내 인사 정보(부서, 직급, 잔여 휴가일, 연락처 등)를 조회합니다.
