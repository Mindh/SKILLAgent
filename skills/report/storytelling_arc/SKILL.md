---
{
  "name": "storytelling_arc",
  "category": "report",
  "type": "llm",
  "display_ko": "스토리 흐름 설계",
  "description": "보고서 흐름을 스토리텔링 구조(SCQA·피라미드·시간순·문제해결)로 설계합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "topic": {
        "type": "string",
        "description": "보고서 주제"
      },
      "audience": {
        "type": "string",
        "description": "대상 청중 (선택)"
      },
      "core_messages": {
        "type": "string",
        "description": "핵심 메시지 리스트 (선택)"
      },
      "structure_preference": {
        "type": "string",
        "description": "선호 구조 (선택: scqa|pyramid|chronological|problem_solution|auto)"
      }
    },
    "required": [
      "topic"
    ]
  }
}
---

# 스토리 흐름 설계

보고서 흐름을 스토리텔링 구조(SCQA·피라미드·시간순·문제해결)로 설계합니다.
