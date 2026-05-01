---
{
  "name": "report_brief_analyzer",
  "category": "report",
  "type": "llm",
  "display_ko": "보고서 의도 분석",
  "description": "사용자의 짧거나 모호한 보고서 요청을 받아 주제·목적·청중·핵심 질문을 정리하고 부족한 정보를 식별합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "rough_input": {
        "type": "string",
        "description": "사용자의 자유 요청 텍스트"
      },
      "known_info": {
        "type": "string",
        "description": "이미 알려진 정보 (선택, JSON 객체 문자열)"
      }
    },
    "required": [
      "rough_input"
    ]
  }
}
---

# 보고서 의도 분석

사용자의 짧거나 모호한 보고서 요청을 받아 주제·목적·청중·핵심 질문을 정리하고 부족한 정보를 식별합니다.
