---
{
  "name": "summarize",
  "category": "hr_text",
  "type": "llm",
  "display_ko": "요약",
  "description": "긴 텍스트를 원문의 30% 이내 분량으로 핵심만 요약합니다.",
  "trigger_keywords": [
    "요약",
    "줄여",
    "핵심만"
  ],
  "parameters": {
    "type": "object",
    "properties": {
      "text": {
        "type": "string",
        "description": "요약할 원문 텍스트"
      }
    },
    "required": [
      "text"
    ]
  }
}
---

# 요약

긴 텍스트를 원문의 30% 이내 분량으로 핵심만 요약합니다.
