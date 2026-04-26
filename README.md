# Skill Base AI

한국 기업 HR 담당자를 위한 **ReAct-style 에이전틱 AI** 시스템입니다.
Function calling을 지원하지 않는 모델에서도 동작하며, 100개 이상의 워크플로우를 동적으로 처리할 수 있습니다.

> **GitHub**: https://github.com/Mindh/SKILLAgent

---

## 특징

- **Function Calling 불필요**: `<tool_call>` 태그 기반 프롬프트 방식으로 도구 호출 — Gemma, Llama 등 자체 호스팅 모델 지원
- **System Role 불필요**: 시스템 프롬프트를 `user/assistant` 교환으로 주입 — 모든 OpenAI 호환 엔드포인트 지원
- **동적 워크플로우 주입**: 워크플로우 정의를 시스템 프롬프트에 하드코딩하지 않고, 사용자 입력에 따라 필요한 워크플로우만 대화에 주입
- **워크플로우 전환**: 워크플로우 진행 중 다른 워크플로우로 전환하고 다시 돌아오는 것을 지원
- **메시지 기반 상태 관리**: 별도 세션 객체 없이 `messages` 리스트 하나로 전체 대화 상태 관리

---

## 빠른 시작

```bash
# 1. 클론
git clone https://github.com/Mindh/SKILLAgent.git
cd SKILLAgent

# 2. 패키지 설치
pip install openai google-genai python-dotenv

# 3. API 키 설정 (둘 중 하나)
export GEMINI_API_KEY="AIzaSy..."          # 환경변수
# 또는 runner/llm.py의 GEMINI_API_KEY 값 직접 수정

# 4. 실행
python runner/run.py                        # 대화형 모드
python runner/run.py "1234 + 5678"          # 단일 실행 모드
```

---

## 아키텍처 개요

```
┌──────────────────────────────────────────────────────────┐
│                   사용자 입력                             │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│              runner/loop.py  (ReAct Loop)                │
│                                                          │
│  ① 첫 턴: 도구 목록 주입 (messages에 1회만)              │
│  ② 워크플로우 검색 → 관련 정의 동적 주입                 │
│  ③ 모델 호출 (system prompt + messages)                  │
│  ④ <tool_call> 감지 → 도구 실행 → 결과 주입 → 재호출    │
│     감지 없음 → 최종 응답 반환                           │
└──────────────────────────────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          │                        │
          ▼                        ▼
┌──────────────────┐    ┌───────────────────────┐
│  runner/tools.py │    │ workflow_retriever.py  │
│                  │    │                        │
│ Python 함수 도구  │    │ 키워드 매칭 (기본)     │
│ - calculator     │    │ 임베딩 검색 (선택)     │
│ - employee_lookup│    │ → agent_registry.json  │
│ - candidate_lookup    │ → definitions/*.md     │
│ - new_employee_  │    └───────────────────────┘
│   lookup         │
│                  │
│ LLM 도구         │
│ - translate      │
│ - summarize      │
│ - jd_generator   │
│ - ... (9개)      │
└──────────────────┘
```

### 단일 턴 실행 흐름

```
[첫 턴]
  messages = []
  → 도구 목록 주입 (messages에 user/assistant 쌍으로 1회)
  → 사용자 입력 관련 워크플로우 검색 및 주입
  → 사용자 메시지 추가
  → 모델 호출

[도구 호출이 있을 때]
  모델 응답에 <tool_call>{"name": "...", "args": {...}}</tool_call> 포함
  → 도구 실행
  → [도구 호출: tool_name] 형태로 중간 응답 저장 (raw 태그 대신)
  → [도구 실행 결과: tool_name] 메시지 주입
  → 모델 재호출 → 최종 응답

[도구 호출이 없을 때]
  → 텍스트 응답을 messages에 저장 후 반환
```

---

## 디렉토리 구조

```
Skill Base AI/
│
├── runner/                         # 실행 엔진
│   ├── run.py                      # 진입점 — run() API + interactive_loop()
│   ├── loop.py                     # ReAct 아gentic 루프 — turn() 핵심 로직
│   ├── tools.py                    # 도구 정의(TOOL_DEFINITIONS) + execute_tool() + get_tool_descriptions()
│   ├── workflow_retriever.py       # 워크플로우 검색 (키워드 / 임베딩)
│   ├── llm.py                      # LLM API 래퍼 — 모델명·엔드포인트 설정 (수정 금지)
│   └── utils.py                    # load_file(), cached_file(), log()
│
├── agents/                         # 워크플로우 정의
│   ├── agent_registry.json         # 워크플로우 메타데이터 + trigger_keywords + 임베딩 캐시
│   └── definitions/                # 워크플로우 상세 절차 문서
│       ├── leave_intake.md             # 휴직 접수
│       ├── recruitment_intake.md       # 채용 요청 접수
│       ├── onboarding_intake.md        # 온보딩 접수
│       └── job_description_writing.md  # 직무기술서 작성
│
├── skills/
│   ├── worker_prompts/             # LLM 도구별 실행 프롬프트
│   │   ├── translate_skill.md
│   │   ├── jd_generator_skill.md
│   │   └── ... (13개)
│   └── tools/                      # Python 함수형 도구
│       ├── calculator_tool.py
│       ├── employee_lookup_tool.py
│       ├── candidate_lookup_tool.py
│       └── new_employee_lookup_tool.py
│
└── prompts/
    └── system_prompt.md            # AI 역할·도구 사용 규칙·워크플로우 원칙
```

---

## 도구 목록 (13개)

### Python 함수형 도구 (4개)

| 도구 | 설명 | 필수 파라미터 |
|------|------|--------------|
| `calculator` | 사칙연산 계산 | `num1`, `num2`, `operator` (+/-/*//) |
| `employee_lookup` | 직원 이름으로 인사 정보 조회 | `employee_name` |
| `candidate_lookup` | 후보자 ID(C-001 형식)로 지원자 정보 조회 | `candidate_id` |
| `new_employee_lookup` | 신규 입사자 ID(N-YYYY-001 형식)로 정보 조회 | `employee_id` |

### LLM 생성형 도구 (9개)

| 도구 | 설명 |
|------|------|
| `translate` | 텍스트를 지정 언어로 번역 (한·영·일·중 등) |
| `summarize` | 텍스트를 원문 30% 이내로 요약 |
| `extract` | 핵심 키워드/항목 최대 5개 추출 |
| `vacation_parser` | 휴가 신청 텍스트에서 이름·기간·사유 구조화 |
| `jd_generator` | 직무 정보 → 채용 공고(JD) 마크다운 초안 생성 |
| `resume_parser` | 자유 형식 이력서 → 학력·경력·기술 구조화 |
| `jd_resume_match_score` | JD ↔ 이력서 매칭 점수(0~100) + 강점/약점 평가 |
| `offer_letter_drafter` | 합격자 정보 → 오퍼레터(처우 제안서) 초안 작성 |
| `onboarding_checklist_generator` | 입사자 정보 → 입사 1주차 체크리스트(5개 카테고리) |

---

## 워크플로우 목록 (4개)

워크플로우는 대화에 하드코딩하지 않습니다. 사용자 입력에서 관련 키워드가 감지되면 해당 워크플로우 정의(`agents/definitions/*.md`)가 자동으로 대화에 주입됩니다.

| 워크플로우 ID | 이름 | 주요 트리거 키워드 | 사용 도구 |
|---|---|---|---|
| `leave_intake` | 휴직 접수 | 휴직, 육아휴직, 병가, 복직 | `employee_lookup` |
| `recruitment_intake` | 채용 요청 접수 | 채용, 공고, 포지션, 지원자 | `jd_generator`, `resume_parser`, `jd_resume_match_score`, `offer_letter_drafter`, `candidate_lookup` |
| `onboarding_intake` | 온보딩 접수 | 온보딩, 입사, 신규 입사자 | `onboarding_checklist_generator`, `new_employee_lookup`, `candidate_lookup` |
| `job_description_writing` | 직무기술서 작성 | 직무기술서, JD, 직무 설명 | — |

---

## 동적 워크플로우 주입 원리

```
사용자: "휴직 신청하고 싶어요"
         │
         ▼
workflow_retriever.retrieve_workflows("휴직 신청하고 싶어요", k=2)
  → 키워드 매칭: "휴직" 포함 → ["leave_intake"]
  → (임베딩 캐시가 있으면 시맨틱 검색으로 업그레이드)
         │
         ▼
messages에 주입:
  {"role": "user",      "content": "[워크플로우 컨텍스트 로드: leave_intake]\n...절차 전문..."}
  {"role": "assistant", "content": "네, 해당 워크플로우 절차를 참고하겠습니다."}
         │
         ▼
모델이 leave_intake 절차에 따라 단계별 안내 시작
```

**워크플로우 전환**: 진행 중에 다른 워크플로우 키워드가 나오면 새 워크플로우를 주입하고, 이전 워크플로우 컨텍스트는 `messages`에 유지되므로 돌아와서 이어갈 수 있습니다.

---

## 임베딩 검색 활성화 (선택)

`agent_registry.json`의 각 항목에 `"embedding"` 필드가 채워져 있으면 키워드 매칭 대신 시맨틱 검색을 사용합니다.

```bash
# 임베딩 사전 계산 예시 (google-genai 필요)
python -c "
from google import genai
import json, os

client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
with open('agents/agent_registry.json') as f:
    registry = json.load(f)

for item in registry:
    if not item.get('embedding'):
        resp = client.models.embed_content(
            model='gemini-embedding-001',
            contents=item['description']
        )
        item['embedding'] = resp.embeddings[0].values

with open('agents/agent_registry.json', 'w', encoding='utf-8') as f:
    json.dump(registry, f, ensure_ascii=False, indent=2)
"
```

임베딩이 없으면 자동으로 `trigger_keywords` 키워드 매칭으로 폴백합니다.

---

## API 사용법

### 단일 턴
```python
from runner.run import run

result = run("1234 + 5678")
print(result["message"])   # "1234와 5678을 더하면 6912입니다."
```

### 멀티턴 (상태 유지)
```python
from runner.run import run

messages = []
injected_workflows = set()

# 첫 번째 턴
result = run("휴직 신청하고 싶어요", messages=messages, injected_workflows=injected_workflows)
messages = result["messages"]
injected_workflows = result["injected_workflows"]
print(result["message"])   # 첫 단계: 직원 이름과 휴직 사유를 묻는 응답

# 두 번째 턴 (상태 이어서)
result = run("김철수, 육아휴직입니다", messages=messages, injected_workflows=injected_workflows)
messages = result["messages"]
injected_workflows = result["injected_workflows"]
print(result["message"])   # 다음 단계 안내
```

### `run()` 반환값

```python
{
    "success": bool,              # 처리 성공 여부
    "message": str,               # AI 응답 텍스트
    "messages": list,             # 갱신된 대화 히스토리 (다음 턴에 전달)
    "injected_workflows": set,    # 이미 주입된 워크플로우 ID 집합 (다음 턴에 전달)
}
```

---

## 모델 및 엔드포인트 설정

`runner/llm.py`에서 모델명과 엔드포인트를 관리합니다. **이 파일만 수정**하면 모델/엔드포인트를 바꿀 수 있습니다.

```python
# runner/llm.py
MODEL_NAME = "gemma-3-27b-it"   # 사용할 모델명

# loop.py에서 참조하는 엔드포인트 (llm.py와 동일하게 유지)
_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
```

자체 호스팅 모델(vLLM, Ollama 등)을 연결하려면 `base_url`을 해당 엔드포인트로 변경합니다. Function calling과 system role을 지원하지 않는 모델도 동작합니다.

---

## 새 워크플로우 추가

1. **`agents/definitions/{workflow_id}.md`** 생성
   - 역할·목적·단계별 절차·주의사항을 자유 형식으로 작성

2. **`agents/agent_registry.json`** 항목 추가
   ```json
   {
     "agent_id": "my_workflow",
     "name": "내 워크플로우",
     "description": "워크플로우 설명 (임베딩 검색에 사용)",
     "trigger_keywords": ["키워드1", "키워드2"],
     "embedding": null
   }
   ```

3. 다음 실행부터 자동으로 키워드 매칭 대상에 포함됩니다.
   임베딩 캐시가 필요하면 위 **임베딩 검색 활성화** 섹션의 스크립트를 실행합니다.

---

## 새 도구 추가

### Python 함수형 도구

1. **`skills/tools/{tool_name}_tool.py`** 생성
   ```python
   def execute(params: dict):
       # params에서 필요한 값 추출 후 처리
       return {"result": "..."}
   ```

2. **`runner/tools.py`**의 `TOOL_DEFINITIONS`에 정의 추가
   ```python
   {
       "type": "function",
       "function": {
           "name": "my_tool",
           "description": "도구 설명",
           "parameters": {
               "type": "object",
               "properties": {
                   "param1": {"type": "string", "description": "설명"},
               },
               "required": ["param1"],
           },
       },
   }
   ```

3. **`runner/tools.py`**의 `_PYTHON_TOOLS` 집합에 도구 이름 추가
   ```python
   _PYTHON_TOOLS = {"calculator", "employee_lookup", ..., "my_tool"}
   ```

### LLM 생성형 도구

1. **`skills/worker_prompts/{tool_name}_skill.md`** 생성 (실행 프롬프트)
2. **`runner/tools.py`**의 `TOOL_DEFINITIONS`에 정의 추가 (`_PYTHON_TOOLS`에는 추가하지 않음)

---

## 동작 검증 시나리오

```bash
# 일반 대화
python runner/run.py "안녕하세요"
# → 자연스러운 인사 응답 (<tool_call> 없음)

# 계산 도구
python runner/run.py "1234 더하기 5678"
# → calculator 호출 → "합계는 6912입니다."

# 직원 조회
python runner/run.py "홍길동 직원 정보 알려줘"
# → employee_lookup 호출 → 인사 정보 안내

# 슬롯 필링 (필수 파라미터 없을 때)
python runner/run.py "직원 조회해줘"
# → 도구 호출 없이 "어느 직원을 조회할까요? 이름을 알려주세요." 응답

# 워크플로우 시작
python runner/run.py "휴직 신청하고 싶어요"
# → leave_intake 워크플로우 주입 → 첫 단계 안내

# 번역 (LLM 도구)
python runner/run.py "이 문장을 영어로 번역해줘: 안녕하세요"
# → translate 호출 → "Hello."
```

---

## 의존성

```bash
pip install openai google-genai python-dotenv
```

| 패키지 | 용도 |
|---|---|
| `openai` | LLM API 호출 (OpenAI 호환 엔드포인트) |
| `google-genai` | 임베딩 검색 사용 시 (`gemini-embedding-001`) — 선택 사항 |
| `python-dotenv` | `.env` 파일에서 API 키 자동 로드 — 선택 사항 |
