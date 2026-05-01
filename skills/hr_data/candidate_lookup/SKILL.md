---
{
  "name": "candidate_lookup",
  "category": "hr_data",
  "type": "python",
  "display_ko": "후보자 정보 조회",
  "description": "채용 후보자 ID(C-001 형식)로 지원자 정보를 조회합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "candidate_id": {
        "type": "string",
        "description": "후보자 ID (예: C-001, C-002)"
      }
    },
    "required": [
      "candidate_id"
    ]
  }
}
---

# 후보자 정보 조회

채용 후보자 ID(C-001 형식)로 지원자 정보를 조회합니다.
