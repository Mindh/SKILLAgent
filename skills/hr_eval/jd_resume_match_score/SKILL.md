---
{
  "name": "jd_resume_match_score",
  "category": "hr_eval",
  "type": "llm",
  "display_ko": "이력서 적합도 평가",
  "description": "채용 공고(JD)와 이력서를 비교하여 0~100 매칭 점수와 추천 여부, 강점/약점을 평가합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "jd_text": {
        "type": "string",
        "description": "채용 공고(JD) 텍스트"
      },
      "resume_text": {
        "type": "string",
        "description": "지원자 이력서 텍스트"
      }
    },
    "required": [
      "jd_text",
      "resume_text"
    ]
  }
}
---

# 이력서 적합도 평가

채용 공고(JD)와 이력서를 비교하여 0~100 매칭 점수와 추천 여부, 강점/약점을 평가합니다.
