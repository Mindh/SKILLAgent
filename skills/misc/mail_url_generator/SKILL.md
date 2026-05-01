---
{
  "name": "mail_url_generator",
  "category": "misc",
  "type": "python",
  "display_ko": "메일 작성 링크 생성",
  "description": "메일 작성 화면을 미리 채워서 여는 mailto: URL을 생성합니다. 사용자가 클릭하면 기본 메일 클라이언트가 열립니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "subject": {
        "type": "string",
        "description": "메일 제목"
      },
      "body": {
        "type": "string",
        "description": "메일 본문 (평문)"
      },
      "to": {
        "type": "string",
        "description": "받는 사람 이메일 주소 (선택)"
      }
    },
    "required": [
      "subject",
      "body"
    ]
  }
}
---

# 메일 작성 링크 생성

메일 작성 화면을 미리 채워서 여는 mailto: URL을 생성합니다. 사용자가 클릭하면 기본 메일 클라이언트가 열립니다.
