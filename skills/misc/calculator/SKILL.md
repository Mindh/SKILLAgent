---
{
  "name": "calculator",
  "category": "misc",
  "type": "python",
  "display_ko": "계산기",
  "description": "두 수의 사칙연산(더하기, 빼기, 곱하기, 나누기)을 계산합니다.",
  "trigger_keywords": [
    "계산",
    "더하",
    "빼",
    "곱하",
    "나누"
  ],
  "parameters": {
    "type": "object",
    "properties": {
      "num1": {
        "type": "number",
        "description": "첫 번째 숫자"
      },
      "num2": {
        "type": "number",
        "description": "두 번째 숫자"
      },
      "operator": {
        "type": "string",
        "enum": [
          "+",
          "-",
          "*",
          "/"
        ],
        "description": "연산자"
      }
    },
    "required": [
      "num1",
      "num2",
      "operator"
    ]
  }
}
---

# 계산기

두 수의 사칙연산(더하기, 빼기, 곱하기, 나누기)을 계산합니다.
