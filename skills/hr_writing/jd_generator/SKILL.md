---
{
  "name": "jd_generator",
  "category": "hr_writing",
  "type": "llm",
  "display_ko": "채용공고 생성",
  "description": "직무 정보를 입력받아 한국 기업 표준 형식의 채용 공고(JD) 마크다운 초안을 생성합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "job_title": {
        "type": "string",
        "description": "직무명 (예: 백엔드 개발자, HR 매니저)"
      },
      "level": {
        "type": "string",
        "description": "직급 또는 연차 (예: 시니어, 3~5년차)"
      },
      "headcount": {
        "type": "integer",
        "description": "채용 인원 수"
      },
      "must_have": {
        "type": "array",
        "items": {
          "type": "string"
        },
        "description": "필수 자격/경험 목록"
      },
      "nice_to_have": {
        "type": "array",
        "items": {
          "type": "string"
        },
        "description": "우대 자격 목록"
      },
      "domain": {
        "type": "string",
        "description": "도메인 또는 팀 (예: 결제, 커머스, HR)"
      },
      "employment_type": {
        "type": "string",
        "description": "근무 형태 (예: 정규직, 계약직)"
      }
    },
    "required": [
      "job_title"
    ]
  }
}
---

# 채용공고 생성

직무 정보를 입력받아 한국 기업 표준 형식의 채용 공고(JD) 마크다운 초안을 생성합니다.
