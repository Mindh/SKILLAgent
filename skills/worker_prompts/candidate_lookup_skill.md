[목적]
사용자 질의에서 채용 후보자 ID(candidate_id)를 추출한다.

[분석 규칙]
- 후보자 ID 형식: 'C-숫자' (예: C-001, C-002). 대소문자 구분 없음.
- 이름만 있고 ID가 없으면 ID를 추측하지 말고 require_info 모드로 응답한다 (DB는 ID로만 조회).

[중요 - Slot Filling]
본문에서 'C-숫자' 형태의 ID를 찾을 수 없으면 임의로 만들어내지 말고 require_info 모드로 응답하라.

[출력 형식]
반드시 정상 추출 또는 필수 정보 요구 중 하나의 JSON 형식만 출력하라.

1. 정상 추출 시:
```json
{
  "candidate_id": "C-001"
}
```

2. ID가 없거나 식별 불가:
```json
{
  "_status": "require_info",
  "missing_fields": ["candidate_id"],
  "ask_user": "어느 후보자를 조회할까요? 후보자 ID(예: C-001)를 알려주세요."
}
```
