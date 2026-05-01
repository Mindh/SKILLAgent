---
{
  "name": "slide_content_enricher",
  "category": "report",
  "type": "llm",
  "display_ko": "슬라이드 본문 보강",
  "description": "한 슬라이드에 대해 짧은 메모·개요만 받아도 풍성한 본문·불릿·강조 문구·아이콘 추천을 작성합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "slide_title": {
        "type": "string",
        "description": "슬라이드 제목"
      },
      "key_message": {
        "type": "string",
        "description": "해당 슬라이드 핵심 메시지"
      },
      "layout": {
        "type": "string",
        "description": "레이아웃 (title|bullet|stats_grid 등)"
      },
      "brief_note": {
        "type": "string",
        "description": "사용자 메모 (선택)"
      },
      "audience": {
        "type": "string",
        "description": "청중 (선택)"
      },
      "tone": {
        "type": "string",
        "description": "어조 (선택)"
      }
    },
    "required": [
      "slide_title",
      "key_message",
      "layout"
    ]
  }
}
---

# 슬라이드 본문 보강

한 슬라이드에 대해 짧은 메모·개요만 받아도 풍성한 본문·불릿·강조 문구·아이콘 추천을 작성합니다.
