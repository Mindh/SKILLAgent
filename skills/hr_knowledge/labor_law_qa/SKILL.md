---
{
  "name": "labor_law_qa",
  "category": "hr_knowledge",
  "type": "llm",
  "display_ko": "노동법 Q&A",
  "description": "한국 노동법(근로기준법·남녀고용평등법·산업안전보건법·최저임금법 등) 관련 질문에 법령 조항 기반으로 답변합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "question": {
        "type": "string",
        "description": "노동법 관련 질문"
      },
      "context": {
        "type": "string",
        "description": "추가 맥락 (선택, 예: '5인 미만 사업장')"
      }
    },
    "required": [
      "question"
    ]
  }
}
---

# 노동법 Q&A

한국 노동법(근로기준법·남녀고용평등법·산업안전보건법·최저임금법 등) 관련 질문에 법령 조항 기반으로 답변합니다.
