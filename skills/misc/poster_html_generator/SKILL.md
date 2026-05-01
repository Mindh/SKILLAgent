---
{
  "name": "poster_html_generator",
  "category": "misc",
  "type": "llm",
  "display_ko": "교육 포스터 생성",
  "description": "교육·행사 입과 안내용 HTML 포스터를 생성합니다. 결과는 완전한 HTML 문서이며 채팅에서 자동으로 미리보기됩니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "training_name": {
        "type": "string",
        "description": "교육명 (예: 신입사원 OJT 교육)"
      },
      "session_name": {
        "type": "string",
        "description": "차수명 (예: 2025년 1차)"
      },
      "location": {
        "type": "string",
        "description": "교육 장소 (예: 본사 3층 교육장)"
      },
      "datetime": {
        "type": "string",
        "description": "교육 일시 (예: 2025-04-15 09:00~18:00)"
      },
      "instructor": {
        "type": "string",
        "description": "강사명"
      },
      "modifications": {
        "type": "string",
        "description": "수정 요청 (선택, 없으면 빈 문자열)"
      }
    },
    "required": [
      "training_name",
      "session_name",
      "location",
      "datetime",
      "instructor"
    ]
  }
}
---

# 교육 포스터 생성

교육·행사 입과 안내용 HTML 포스터를 생성합니다. 결과는 완전한 HTML 문서이며 채팅에서 자동으로 미리보기됩니다.
