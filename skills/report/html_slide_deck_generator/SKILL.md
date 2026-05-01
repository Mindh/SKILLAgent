---
{
  "name": "html_slide_deck_generator",
  "category": "report",
  "type": "llm",
  "display_ko": "HTML 슬라이드덱 생성",
  "description": "보고서 개요·콘텐츠를 받아 완성된 HTML 슬라이드 덱(방향키 네비게이션, 13가지 레이아웃, 인라인 SVG 인포그래픽)을 생성합니다. 결과는 채팅에서 자동 미리보기됩니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "report_title": {
        "type": "string",
        "description": "보고서 제목"
      },
      "subtitle": {
        "type": "string",
        "description": "부제 (선택)"
      },
      "theme_color": {
        "type": "string",
        "description": "메인 색상 hex (예: #2563EB)"
      },
      "author": {
        "type": "string",
        "description": "작성자/팀 (선택)"
      },
      "slides": {
        "type": "string",
        "description": "슬라이드 정보 배열 (JSON 문자열)"
      },
      "modifications": {
        "type": "string",
        "description": "수정 요청 (선택)"
      }
    },
    "required": [
      "report_title",
      "theme_color",
      "slides"
    ]
  }
}
---

# HTML 슬라이드덱 생성

보고서 개요·콘텐츠를 받아 완성된 HTML 슬라이드 덱(방향키 네비게이션, 13가지 레이아웃, 인라인 SVG 인포그래픽)을 생성합니다. 결과는 채팅에서 자동 미리보기됩니다.
