---
{
  "name": "expense_calculator",
  "category": "hr_data",
  "type": "python",
  "display_ko": "출장비 견적",
  "description": "출장비 견적을 도시·교통수단·일수·직급에 따라 계산합니다. 식비·숙박비·교통비를 분리해 합산.",
  "trigger_keywords": [
    "출장비",
    "견적",
    "출장 경비"
  ],
  "parameters": {
    "type": "object",
    "properties": {
      "destination": {
        "type": "string",
        "description": "출장지 (예: 부산, 도쿄, 뉴욕)"
      },
      "days": {
        "type": "integer",
        "description": "출장 일수"
      },
      "transport": {
        "type": "string",
        "description": "교통수단 (ktx, 고속버스, 비행기_국내, 비행기_국제, 자가용)"
      },
      "origin": {
        "type": "string",
        "description": "출발지 (선택, 기본 서울)"
      },
      "level": {
        "type": "string",
        "description": "직급 (선택, 단가 보정에 사용)"
      }
    },
    "required": [
      "destination",
      "days"
    ]
  }
}
---

# 출장비 견적

출장비 견적을 도시·교통수단·일수·직급에 따라 계산합니다. 식비·숙박비·교통비를 분리해 합산.
