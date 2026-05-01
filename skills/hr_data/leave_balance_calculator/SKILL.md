---
{
  "name": "leave_balance_calculator",
  "category": "hr_data",
  "type": "python",
  "display_ko": "잔여 휴가 계산",
  "description": "직원의 입사일과 사용한 휴가 일수를 기준으로 잔여 연차 일수를 계산합니다. employee_name으로 DB 조회하거나 join_date를 직접 지정.",
  "trigger_keywords": [
    "잔여 휴가",
    "연차 잔여",
    "남은 휴가"
  ],
  "parameters": {
    "type": "object",
    "properties": {
      "employee_name": {
        "type": "string",
        "description": "직원 이름 (DB 조회용, 선택)"
      },
      "join_date": {
        "type": "string",
        "description": "입사일 (YYYY-MM-DD, 직접 지정용)"
      },
      "used_days": {
        "type": "integer",
        "description": "사용한 휴가 일수 (선택, 기본 0 또는 DB 값)"
      }
    },
    "required": []
  }
}
---

# 잔여 휴가 계산

직원의 입사일과 사용한 휴가 일수를 기준으로 잔여 연차 일수를 계산합니다. employee_name으로 DB 조회하거나 join_date를 직접 지정.
