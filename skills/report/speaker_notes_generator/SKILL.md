---
{
  "name": "speaker_notes_generator",
  "category": "report",
  "type": "llm",
  "display_ko": "발표 스크립트 작성",
  "description": "각 슬라이드 내용을 받아 발표자용 1~2분 분량 구어체 발표 스크립트를 작성합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "slides": {
        "type": "string",
        "description": "슬라이드 정보 배열 (JSON 문자열)"
      },
      "audience": {
        "type": "string",
        "description": "청중 (선택)"
      },
      "duration_per_slide_sec": {
        "type": "integer",
        "description": "슬라이드당 발표 시간 초 (선택, 기본 90)"
      }
    },
    "required": [
      "slides"
    ]
  }
}
---

# 발표 스크립트 작성

각 슬라이드 내용을 받아 발표자용 1~2분 분량 구어체 발표 스크립트를 작성합니다.
