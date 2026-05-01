---
{
  "name": "vacation_parser",
  "category": "hr_text",
  "type": "llm",
  "display_ko": "휴가 정보 추출",
  "description": "휴가 신청 텍스트에서 직원 이름, 시작일, 종료일, 사유를 구조화하여 추출합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "text": {
        "type": "string",
        "description": "휴가 신청 내용이 담긴 텍스트"
      }
    },
    "required": [
      "text"
    ]
  }
}
---

# 휴가 정보 추출

휴가 신청 텍스트에서 직원 이름, 시작일, 종료일, 사유를 구조화하여 추출합니다.
