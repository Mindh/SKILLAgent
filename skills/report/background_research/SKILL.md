---
{
  "name": "background_research",
  "category": "report",
  "type": "llm",
  "display_ko": "배경·맥락 조사",
  "description": "보고서 주제에 대한 배경·시장 맥락·트렌드·핵심 사실을 LLM 학습 지식 범위에서 정리합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "topic": {
        "type": "string",
        "description": "보고서 주제"
      },
      "scope": {
        "type": "string",
        "description": "조사 범위 (선택)"
      },
      "depth": {
        "type": "string",
        "description": "조사 깊이 (선택: summary|detailed)"
      }
    },
    "required": [
      "topic"
    ]
  }
}
---

# 배경·맥락 조사

보고서 주제에 대한 배경·시장 맥락·트렌드·핵심 사실을 LLM 학습 지식 범위에서 정리합니다.
