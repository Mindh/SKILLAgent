# Skill Base AI

모듈형 스킬 레지스트리 기반의 **ReAct(Reasoning and Acting) 에이전틱 AI** 시스템입니다.
사용자의 요청을 분석하여 적절한 스킬을 동적으로 선택·실행하고, 결과를 스스로 평가·개선하는 자율 실행 루프를 갖추고 있습니다.

> **GitHub**: https://github.com/Mindh/SKILLAgent

---

## 빠른 시작 (Linux 서버 클론 배포)

```bash
# 1. 클론
git clone https://github.com/Mindh/SKILLAgent.git
cd SKILLAgent

# 2. 패키지 설치
pip install -r requirements.txt

# 3. API 키 설정
cp .env.example .env
nano .env          # GEMINI_API_KEY=여기에_키_입력

# 4. 실행
python runner/run.py                          # 대화형 모드
python runner/run.py "이 텍스트를 번역해줘"   # 단일 실행 모드
```

> **첫 실행 시** `ensure_index_ready()`가 자동으로 스킬 임베딩을 계산하고
> `skills/skill_registry.json`에 캐싱합니다. 이후 실행부터는 API 재호출 없이 즉시 사용됩니다.

---


## 디렉토리 구조

```
Skill Base AI/
│
├── runner/                         # 핵심 실행 엔진
│   ├── run.py                      # 메인 실행 루프 (ReAct while 루프)
│   ├── router.py                   # 다음 행동 결정 (RAG + LLM 라우터)
│   ├── skill_retriever.py          # 임베딩 기반 스킬 검색 엔진 (RAG)
│   ├── components.py               # 스킬 실행 / Judge / Refine 컴포넌트
│   ├── llm.py                      # LLM API 호출 래퍼 (Gemini)
│   └── utils.py                    # 공통 유틸리티 (파싱, 로깅, 설정 로드)
│
├── skills/                         # 스킬 정의 및 자산
│   ├── skill_registry.json         # 스킬 메타데이터 + 임베딩 벡터 캐시 (RAG 인덱스)
│   ├── skill_registry.md           # (레거시) 마크다운 형식 스킬 목록
│   │
│   ├── worker_prompts/             # 각 스킬의 실행 프롬프트
│   │   ├── translate_skill.md
│   │   ├── summarize_skill.md
│   │   ├── extract_skill.md
│   │   ├── calculator_skill.md
│   │   ├── vacation_parser_skill.md
│   │   └── employee_lookup_skill.md
│   │
│   ├── system_prompts/             # Judge / Refine 공통 시스템 프롬프트
│   │   ├── judge_skill.md
│   │   └── refine_skill.md
│   │
│   └── tools/                      # 함수형 스킬 실행 모듈 (Python)
│       ├── calculator_tool.py
│       └── employee_lookup_tool.py
│
└── prompts/                        # 시스템 공통 프롬프트 및 설정
    ├── base_system.md              # AI 어시스턴트 기본 페르소나
    ├── router_prompt.md            # 라우터 LLM 지시 프롬프트
    └── loop_config.md              # 실행 파라미터 설정 파일
```

---

## 핵심 아키텍처: ReAct 루프

시스템은 사용자의 요청을 처리하기 위해 **Reasoning → Acting → Observation** 사이클을 반복합니다.

```
사용자 입력
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│              while step_count < MAX_STEPS                    │
│                                                              │
│  [1] RAG Retrieval                                           │
│      user_input 임베딩 → skill_registry.json과 코사인 유사도 계산  │
│      → 가장 관련성 높은 Top-K 스킬만 후보 풀로 선택               │
│                                                              │
│  [2] Router (Reasoning)                                      │
│      LLM이 {Top-K 후보 풀} + {global_state} + {사용자 요청}을 보고  │
│      "지금 당장 실행할 단 하나의 스킬"을 JSON으로 결정              │
│      → 완료 판단 시: 평문 텍스트 반환 (Fast-Track chat break)      │
│                                                              │
│  [3] Skill Execution (Acting)                                │
│      선택된 스킬 유형에 따라 분기:                                │
│      ├─ LLM 스킬 (translate 등): worker_prompt + call_ai()    │
│      └─ 툴 스킬 (calculator 등): tool.py의 execute() 함수 호출  │
│                                                              │
│  [4] Judge / Refine (Self-Evaluation)                        │
│      LLM 스킬에만 적용:                                        │
│      judge_skill.md로 품질 점수(0~10) 평가                      │
│      → pass_threshold 미달 시: refine_skill.md으로 자가 수정     │
│      → 최대 max_iterations 회 반복                             │
│                                                              │
│  [5] Observation & State Update                              │
│      실행 결과를 global_state[skill_id]에 저장                   │
│      → 다음 루프에서 라우터가 "무엇이 완료됐는지" 파악하는 근거        │
│                                                              │
│  [6] 종료 판단                                                │
│      ├─ LLM 스킬 + judge pass → 즉시 break (조기 종료)           │
│      ├─ 툴 스킬 → loop 재진입 (결과 제시용 chat 필요)              │
│      ├─ Router가 "chat" 반환 → break                          │
│      └─ step_count >= MAX_STEPS → 강제 종료                    │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
최종 결과 반환
```

---

## 등록된 스킬 목록

| skill_id | 타입 | 설명 |
|---|---|---|
| `translate` | LLM 스킬 | 텍스트를 지정 언어로 번역 |
| `summarize` | LLM 스킬 | 텍스트를 핵심 내용으로 요약 |
| `extract` | LLM 스킬 | 핵심 키워드/항목 추출 |
| `calculator` | 툴 스킬 | 수식 파싱 및 계산 (`calculator_tool.py`) |
| `vacation_parser` | LLM 스킬 | 휴가 신청 정보(날짜·기간·사유) 구조화 |
| `employee_lookup` | 툴 스킬 | 사내 직원 인사 정보 조회 (`employee_lookup_tool.py`) |
| `chat` | 내장 | 일반 대화 응답 / 파이프라인 종료 신호 |

---

## 주요 컴포넌트 상세

### 1. RAG 기반 스킬 검색 (`skill_retriever.py`)

스킬이 수십~수백 개로 늘어나도 토큰 초과 없이 관련 스킬만 라우터에 주입합니다.

```
최초 실행 시:
  skill_registry.json 로드
  → embedding=null인 스킬만 Gemini Embedding API 호출 (gemini-embedding-001)
  → 3072차원 벡터를 skill_registry.json에 캐싱 (이후 재호출 없음)

매 요청 시:
  user_input → 임베딩 → 저장된 스킬 벡터들과 코사인 유사도 계산
  → 상위 K개 스킬의 설명 텍스트 블록 생성 → 라우터 프롬프트에 주입

폴백 전략: embedding 실패 → keyword 매칭 → 전체 레지스트리 반환
```

**설정 (`loop_config.md`):**
- `skill_retrieval_mode`: `embedding` | `keyword` | `full`
- `skill_retrieval_top_k`: 라우터에 제공할 최대 스킬 수 (기본값: 3)

### 2. 동적 라우터 (`router.py`)

매 루프마다 **단 하나의 Next Action**만 결정합니다. 전체 계획을 미리 세우지 않습니다.

- **입력:** `{Top-K 스킬 블록}` + `{global_state}` + `{사용자 요청}` + `{대화 기록}`
- **출력:**
  - JSON → 다음 실행할 스킬 선택
  - 평문 텍스트 → 작업 완료 / 일반 대화 (Fast-Track, 추가 LLM 호출 없음)

### 3. 스킬 실행 분기 (`components.py`)

```python
# 툴 스킬: tools/{skill_id}_tool.py 존재 시
tool_module.execute(params)   # Python 함수 직접 호출 (확실한 결과 보장)

# LLM 스킬: 없으면 LLM 텍스트 추론
call_ai(system=worker_prompt, user=input)
```

**툴 스킬 자가 치유 (Self-Healing):**
파라미터 생성 실패(JSON 파싱 에러) 또는 함수 실행 예외 발생 시, 에러 내용을 LLM에 피드백하여 최대 `max_iterations`회 재시도합니다.

### 4. Judge / Refine 루프 (`run.py`)

LLM 스킬 결과에만 적용되는 자가 평가·개선 사이클입니다.

```
judge_skill.md  → 출력 품질을 0~10점으로 채점
   score >= pass_threshold (기본: 7) → 통과 → 즉시 break
   score < threshold        → refine_skill.md로 피드백 기반 재생성
   max_iterations (기본: 3) 소진 → 강제 통과
```

### 5. Global State (작업 메모리)

```python
# 실행 결과가 skill_id를 키로 누적 저장됩니다
global_state = {
    "employee_lookup": {
        "function_result": {"name": "김철수", "dept": "개발팀", "annual_leave": 5},
        "extracted_params": {"employee_name": "김철수"}
    },
    "summarize": {
        "summary": "김철수는 개발팀 소속이며 잔여 연차 5일"
    }
}
```

라우터는 `global_state`를 보고 "무엇이 완료됐는지" 파악하여 다음 행동을 결정합니다.
비어 있으면 → 스킬 선택, 결과가 있으면 → 완료 또는 다음 스킬 판단.

### 6. Slot Filling (필수 정보 요청)

스킬/툴이 필수 파라미터 부재를 감지하면 `_status: "require_info"`를 반환합니다.
시스템은 파이프라인을 일시 중단하고 사용자에게 추가 정보를 요청한 후 재개합니다.

---

## 설정 파일 (`prompts/loop_config.md`)

```
max_iterations: 3           # Judge/Refine 최대 반복 횟수
pass_threshold: 7           # Judge 통과 기준 점수 (0~10)
force_exit_on_max: true     # 반복 한도 도달 시 강제 종료
context_window: last_2      # Refine 시 참조할 이전 피드백 수
temperature: 0              # LLM 생성 온도 (0 = 결정론적)
skill_retrieval_top_k: 3    # RAG로 라우터에 제공할 스킬 후보 수
skill_retrieval_mode: embedding  # 검색 모드: embedding | keyword | full
```

---

## 실행 방법

### 대화형 모드
```bash
python runner/run.py
```

### 단일 실행 모드
```bash
python runner/run.py "이 텍스트를 영어로 번역해줘: 안녕하세요"
```

### API 모드 (다른 모듈에서 import)
```python
from runner.run import run

result = run(
    user_input="김철수 직원 정보 조회해줘",
    history=[],           # 이전 대화 기록 (선택)
    global_state={}       # 작업 상태 공간 (선택, 멀티턴 시 유지)
)

# 반환값 구조
{
    "success": True,
    "pipeline_plan": [...],    # 실행된 스킬 계획 목록
    "pipeline_results": [...], # 각 스킬의 실행 결과 상세
    "output": {...},           # 최종 출력 ({"response": "..."} 형태)
    "raw_output": "...",       # 최종 스킬의 raw 출력
    "iterations": 2            # 총 Judge/Refine 반복 횟수
}
```

---

## 새 스킬 추가 방법

1. **`skills/worker_prompts/{skill_id}_skill.md`** — 스킬 실행 프롬프트 및 출력 JSON 형식 정의
2. **`skills/skill_registry.json`** — 스킬 항목 추가 (`embedding: null`로 설정, 자동 계산됨)
3. **(툴 스킬인 경우)** **`skills/tools/{skill_id}_tool.py`** — `execute(params: dict) -> any` 함수 구현
4. **`runner/run.py`의 `_make_final_response()`** — 스킬별 출력 포맷 규칙 추가 (선택)

> 스킬을 추가하면 다음 실행 시 `ensure_index_ready()`가 자동으로 임베딩을 계산하고 캐싱합니다.

---

## 의존성

```bash
pip install openai google-genai
```

| 패키지 | 용도 |
|---|---|
| `openai` | Gemini API 호출 (OpenAI 호환 엔드포인트) |
| `google-genai` | Gemini Embedding API (`gemini-embedding-001`) |

**API 키 설정:** `runner/llm.py`의 `GEMINI_API_KEY` 상수 또는 환경변수 `GEMINI_API_KEY`
