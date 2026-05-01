---
{
  "name": "extract",
  "category": "hr_text",
  "type": "llm",
  "display_ko": "키워드 추출",
  "description": "텍스트에서 핵심 키워드나 항목을 최대 5개 추출합니다.",
  "trigger_keywords": [
    "키워드",
    "추출",
    "뽑아"
  ],
  "parameters": {
    "type": "object",
    "properties": {
      "text": {
        "type": "string",
        "description": "분석할 원문 텍스트"
      }
    },
    "required": [
      "text"
    ]
  }
}
---

# 키워드 추출

텍스트에서 핵심 키워드나 항목을 최대 5개 추출합니다.
