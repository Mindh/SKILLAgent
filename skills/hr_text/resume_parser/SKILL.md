---
{
  "name": "resume_parser",
  "category": "hr_text",
  "type": "llm",
  "display_ko": "이력서 분석",
  "description": "자유 형식의 이력서 텍스트를 학력·경력·기술 스택 등 구조화된 형태로 변환합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "resume_text": {
        "type": "string",
        "description": "분석할 이력서 원문 텍스트"
      }
    },
    "required": [
      "resume_text"
    ]
  }
}
---

# 이력서 분석

자유 형식의 이력서 텍스트를 학력·경력·기술 스택 등 구조화된 형태로 변환합니다.
