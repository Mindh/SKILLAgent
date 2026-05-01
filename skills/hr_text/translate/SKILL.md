---
{
  "name": "translate",
  "category": "hr_text",
  "type": "llm",
  "display_ko": "번역",
  "description": "텍스트를 지정한 언어로 번역합니다. 한국어, 영어, 일본어, 중국어 등을 지원합니다.",
  "trigger_keywords": [
    "번역",
    "translate",
    "영어로",
    "한국어로"
  ],
  "parameters": {
    "type": "object",
    "properties": {
      "text": {
        "type": "string",
        "description": "번역할 원문 텍스트"
      },
      "target_lang": {
        "type": "string",
        "description": "목표 언어 (예: Korean, English, Japanese). 기본값: English"
      }
    },
    "required": [
      "text"
    ]
  }
}
---

# 번역

텍스트를 지정한 언어로 번역합니다. 한국어, 영어, 일본어, 중국어 등을 지원합니다.
