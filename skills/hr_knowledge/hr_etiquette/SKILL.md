---
{
  "name": "hr_etiquette",
  "category": "hr_knowledge",
  "type": "llm",
  "display_ko": "직장 매너 조언",
  "description": "한국 직장 커뮤니케이션·매너에 대한 조언을 제공합니다 (메일·메신저·대면 상황별 권장 표현).",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "situation": {
        "type": "string",
        "description": "상황 설명"
      },
      "relation": {
        "type": "string",
        "description": "상대 관계 (선택: 상급자|동료|후배|외부 거래처)"
      },
      "channel": {
        "type": "string",
        "description": "소통 채널 (선택: 대면|메신저|메일|전화)"
      }
    },
    "required": [
      "situation"
    ]
  }
}
---

# 직장 매너 조언

한국 직장 커뮤니케이션·매너에 대한 조언을 제공합니다 (메일·메신저·대면 상황별 권장 표현).
