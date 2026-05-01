---
{
  "name": "audience_analyzer",
  "category": "report",
  "type": "llm",
  "display_ko": "청중 분석",
  "description": "대상 청중(임원/신입/투자자/외부 등)에 맞는 톤·강조점·피해야 할 표현·예상 질문을 분석합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "audience": {
        "type": "string",
        "description": "대상 청중"
      },
      "topic": {
        "type": "string",
        "description": "보고서 주제 (선택)"
      },
      "context": {
        "type": "string",
        "description": "추가 맥락 (선택)"
      }
    },
    "required": [
      "audience"
    ]
  }
}
---

# 청중 분석

대상 청중(임원/신입/투자자/외부 등)에 맞는 톤·강조점·피해야 할 표현·예상 질문을 분석합니다.
