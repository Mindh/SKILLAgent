---
{
  "name": "performance_review_template_generator",
  "category": "hr_eval",
  "type": "llm",
  "display_ko": "평가 양식 생성",
  "description": "직급·부서·평가 종류(자기/동료/상급자/다면)에 맞춰 인사 평가 양식을 설계합니다. 섹션·가중치·문항 자동 구성.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "target_level": {
        "type": "string",
        "description": "평가 대상 직급 (예: 사원, 대리, 과장, 팀장)"
      },
      "department": {
        "type": "string",
        "description": "소속 부서 (선택)"
      },
      "review_type": {
        "type": "string",
        "description": "평가 종류 (자기평가|동료평가|상급자평가|다면평가)"
      },
      "review_period": {
        "type": "string",
        "description": "평가 기간 (선택, 예: 2025년 상반기)"
      },
      "focus_areas": {
        "type": "string",
        "description": "특별 강조 영역 (선택)"
      }
    },
    "required": [
      "target_level",
      "review_type"
    ]
  }
}
---

# 평가 양식 생성

직급·부서·평가 종류(자기/동료/상급자/다면)에 맞춰 인사 평가 양식을 설계합니다. 섹션·가중치·문항 자동 구성.
