---
{
  "name": "announcement_writer",
  "category": "hr_writing",
  "type": "llm",
  "display_ko": "사내 공지문 작성",
  "description": "사내 공지문(이메일·슬랙·게시판)을 주제·톤·대상에 맞춰 작성합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "topic": {
        "type": "string",
        "description": "공지 주제 (예: 여름휴가 안내)"
      },
      "audience": {
        "type": "string",
        "description": "대상자 (선택, 기본 전 직원)"
      },
      "tone": {
        "type": "string",
        "description": "톤 (선택: 공식적|친근한|긴급)"
      },
      "key_info": {
        "type": "string",
        "description": "공지에 반드시 포함할 핵심 정보 (선택)"
      },
      "channel": {
        "type": "string",
        "description": "배포 채널 (선택: 이메일|슬랙|사내 게시판)"
      }
    },
    "required": [
      "topic"
    ]
  }
}
---

# 사내 공지문 작성

사내 공지문(이메일·슬랙·게시판)을 주제·톤·대상에 맞춰 작성합니다.
