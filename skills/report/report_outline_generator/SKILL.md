---
{
  "name": "report_outline_generator",
  "category": "report",
  "type": "llm",
  "display_ko": "보고서 개요 생성",
  "description": "보고서 주제·청중·스토리 구조를 받아 슬라이드별 상세 개요(섹션 제목·핵심 메시지·권장 레이아웃·시각화)를 생성합니다.",
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
        "description": "대상 청중"
      },
      "slide_count": {
        "type": "integer",
        "description": "원하는 슬라이드 개수 (보통 8~20)"
      },
      "core_messages": {
        "type": "string",
        "description": "핵심 메시지 리스트 (선택)"
      },
      "story_arc": {
        "type": "string",
        "description": "스토리 흐름 단계 (선택)"
      },
      "background": {
        "type": "string",
        "description": "배경 자료 요약 (선택)"
      },
      "additional_context": {
        "type": "string",
        "description": "사용자 추가 메모 (선택)"
      }
    },
    "required": [
      "topic",
      "audience",
      "slide_count"
    ]
  }
}
---

# 보고서 개요 생성

보고서 주제·청중·스토리 구조를 받아 슬라이드별 상세 개요(섹션 제목·핵심 메시지·권장 레이아웃·시각화)를 생성합니다.
