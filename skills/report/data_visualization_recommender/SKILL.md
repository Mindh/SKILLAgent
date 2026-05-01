---
{
  "name": "data_visualization_recommender",
  "category": "report",
  "type": "llm",
  "display_ko": "데이터 시각화 추천",
  "description": "데이터 유형·요약·강조 인사이트를 받아 가장 효과적인 차트·인포그래픽 종류를 추천합니다.",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {
      "data_type": {
        "type": "string",
        "description": "데이터 유형 (시계열|카테고리 비교|구성비|관계|지리적 등)"
      },
      "data_summary": {
        "type": "string",
        "description": "데이터 한 줄 요약"
      },
      "key_insight": {
        "type": "string",
        "description": "강조하고 싶은 인사이트 (선택)"
      },
      "audience": {
        "type": "string",
        "description": "청중 (선택)"
      }
    },
    "required": [
      "data_type",
      "data_summary"
    ]
  }
}
---

# 데이터 시각화 추천

데이터 유형·요약·강조 인사이트를 받아 가장 효과적인 차트·인포그래픽 종류를 추천합니다.
