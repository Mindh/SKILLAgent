---
{
  "name": "key_message_extractor",
  "category": "report",
  "type": "llm",
  "display_ko": "핵심 메시지 추출",
  "description": "사용자가 제공한 자료/메모에서 보고서의 핵심 메시지 3~5개를 우선순위와 함께 추출합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "raw_content": {
        "type": "string",
        "description": "사용자 자료/메모 (자유 텍스트)"
      },
      "topic": {
        "type": "string",
        "description": "보고서 주제 (선택)"
      },
      "audience": {
        "type": "string",
        "description": "청중 (선택)"
      }
    },
    "required": [
      "raw_content"
    ]
  }
}
---

# 핵심 메시지 추출

사용자가 제공한 자료/메모에서 보고서의 핵심 메시지 3~5개를 우선순위와 함께 추출합니다.
