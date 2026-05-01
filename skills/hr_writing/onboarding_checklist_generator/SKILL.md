---
{
  "name": "onboarding_checklist_generator",
  "category": "hr_writing",
  "type": "llm",
  "display_ko": "온보딩 체크리스트 생성",
  "description": "신규 입사자 정보를 받아 서류·계정·교육·미팅·문서권한 5개 카테고리의 입사 1주차 체크리스트를 생성합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "employee_name": {
        "type": "string",
        "description": "입사자 이름"
      },
      "position": {
        "type": "string",
        "description": "직무"
      },
      "level": {
        "type": "string",
        "description": "직급"
      },
      "department": {
        "type": "string",
        "description": "배치 부서"
      },
      "start_date": {
        "type": "string",
        "description": "입사일"
      }
    },
    "required": [
      "employee_name"
    ]
  }
}
---

# 온보딩 체크리스트 생성

신규 입사자 정보를 받아 서류·계정·교육·미팅·문서권한 5개 카테고리의 입사 1주차 체크리스트를 생성합니다.
