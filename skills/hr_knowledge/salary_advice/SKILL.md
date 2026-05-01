---
{
  "name": "salary_advice",
  "category": "hr_knowledge",
  "type": "llm",
  "display_ko": "연봉/보상 조언",
  "description": "한국 IT·서비스 업계 보상(연봉·인센티브·퇴직금) 시장 수준과 협상 조언을 제공합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "topic": {
        "type": "string",
        "description": "질문 주제"
      },
      "job_role": {
        "type": "string",
        "description": "직무 (선택)"
      },
      "level": {
        "type": "string",
        "description": "직급/연차 (선택)"
      },
      "company_size": {
        "type": "string",
        "description": "회사 규모 (선택: 스타트업|중견기업|대기업)"
      },
      "region": {
        "type": "string",
        "description": "지역 (선택, 기본 수도권)"
      }
    },
    "required": [
      "topic"
    ]
  }
}
---

# 연봉/보상 조언

한국 IT·서비스 업계 보상(연봉·인센티브·퇴직금) 시장 수준과 협상 조언을 제공합니다.
