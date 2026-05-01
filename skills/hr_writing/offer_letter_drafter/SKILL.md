---
{
  "name": "offer_letter_drafter",
  "category": "hr_writing",
  "type": "llm",
  "display_ko": "오퍼레터 작성",
  "description": "합격자 정보를 입력받아 공식 오퍼레터(처우 제안서) 초안을 한국어로 작성합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "candidate_name": {
        "type": "string",
        "description": "합격자 이름"
      },
      "position": {
        "type": "string",
        "description": "직무명"
      },
      "level": {
        "type": "string",
        "description": "직급"
      },
      "annual_salary": {
        "type": "integer",
        "description": "연봉 (단위: 만원)"
      },
      "start_date": {
        "type": "string",
        "description": "입사 예정일 (예: 2025-03-01)"
      },
      "department": {
        "type": "string",
        "description": "배치 부서"
      }
    },
    "required": [
      "candidate_name",
      "position"
    ]
  }
}
---

# 오퍼레터 작성

합격자 정보를 입력받아 공식 오퍼레터(처우 제안서) 초안을 한국어로 작성합니다.
