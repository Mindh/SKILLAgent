# Skill Base AI

업무 프로세스 Agent + 모듈형 Skill을 결합한 **3-tier 에이전틱 AI** 시스템입니다.
사용자의 요청을 Supervisor가 판단해 **단발 Skill 실행 / Agent 활성화 / 일반 대화** 중 적절한 액션으로 라우팅하고, 다단계 업무 프로세스는 Agent가 상태를 유지하며 끝까지 진행합니다.

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

> **첫 실행 시** `_init_runtime()`이 임베딩 가용성을 감지하고, Skill·Agent 레지스트리에 임베딩을 1회 계산해 캐싱합니다. 임베딩 모델을 못 쓰는 환경에서는 자동으로 keyword 매칭 모드로 폴백합니다.

---

## 3-tier 아키텍처 한눈에

```
┌────────────────────────────────────────────────────────────┐
│                    Supervisor                               │
│  매 턴 진입점. LLM이 4개 action 중 하나를 결정:             │
│   ① continue_agent   ② switch_agent                        │
│   ③ call_skill       ④ chat                                │
└─────────────┬────────────────────────────┬─────────────────┘
              │                            │
        (다단계 프로세스)            (단발 작업)
              │                            │
   ┌──────────▼──────────┐         ┌──────▼──────┐
   │      Agent          │ ──────▶ │   Skill     │
   │ workflow 단계 진행  │ skill   │ LLM-only 또는│
   │ collected_data 누적 │ chain   │ 함수형 (tool) │
   │ bubble_up 신호 반환 │ ◀──────  │             │
   └─────────────────────┘ result  └─────────────┘
```

- **Supervisor** (`runner/supervisor.py`) — 세션 최상위 오케스트레이터. `active_agent`, `paused_agents`, `pending_switch`, `pending_skill` 상태 관리.
- **Agent** (`runner/agent_runner.py`) — 다단계 업무 프로세스(예: 휴직 접수, 채용 요청). 한 턴에 한 단계 진행, 필요한 정보를 사용자에게 묻고 collected_data에 축적. 범위 밖 요청은 `bubble_up`으로 Supervisor에 제어권 반환.
- **Skill** (`runner/components.py::run_skill`) — 재사용 가능한 atomic 단위. LLM-only(prompt만)과 함수형(prompt + `tool.py`) 두 종류.

---

## 디렉토리 구조

```
Skill Base AI/
│
├── runner/                         # 실행 엔진
│   ├── run.py                      # 진입점 (supervisor.turn() 호출)
│   ├── supervisor.py               # 세션 오케스트레이터, 4-action 디스패치
│   ├── agent_runner.py             # Active agent 한 턴 실행 + skill 체이닝
│   ├── components.py               # run_skill / run_judge / run_refine
│   ├── retriever.py                # 제네릭 Top-K RAG 엔진 (skill·agent 공용)
│   ├── skill_retriever.py          # Skill 레지스트리 어댑터
│   ├── agent_retriever.py          # Agent 레지스트리 어댑터
│   ├── embeddings.py               # 임베딩·코사인 유사도·가용성 감지
│   ├── llm.py                      # LLM API 호출 래퍼 (Gemini OpenAI 호환)
│   └── utils.py                    # parse_json(균형 추출 폴백), cached_file, log
│
├── agents/                         # 업무 프로세스 Agent 자산
│   ├── agent_registry.json         # Agent 메타데이터 + 임베딩 캐시
│   └── definitions/                # Agent 역할·workflow·JSON I/O 스키마
│       ├── leave_intake.md             # 휴직 접수 (9단계)
│       ├── job_description_writing.md  # 직무기술서 작성 (4단계)
│       ├── recruitment_intake.md       # 채용 요청 접수 (7단계)
│       └── onboarding_intake.md        # 입사 절차 접수 (5단계)
│
├── skills/                         # Skill 자산
│   ├── skill_registry.json         # Skill 메타데이터 + 임베딩 캐시
│   ├── worker_prompts/             # 각 Skill의 추출/실행 프롬프트
│   ├── system_prompts/             # Judge / Refine 공통 프롬프트
│   └── tools/                      # 함수형 Skill의 Python 모듈 (DUMMY_DB 포함)
│
└── prompts/                        # 시스템 공통 프롬프트
    ├── base_system.md              # 기본 페르소나
    ├── supervisor_prompt.md        # Supervisor 의사결정 지시
    └── loop_config.md              # 실행 파라미터
```

---

## 등록된 Agent

| agent_id | 단계 수 | 설명 | 사용 가능한 Skill |
|---|---|---|---|
| `leave_intake` | 9 | 휴직 접수 (면담→자격확인→서류→부서장→메일→검증→휴직원→행정→발령) | `employee_lookup` |
| `job_description_writing` | 4 | 직무기술서 작성 양식 생성·취합·업로드 | — |
| `recruitment_intake` | 7 | 채용 요청 → 포지션 정의 → JD 초안 → 스크리닝 → 오퍼 준비 | `jd_generator`, `resume_parser`, `jd_resume_match_score`, `offer_letter_drafter`, `candidate_lookup` |
| `onboarding_intake` | 5 | 합격자 정보 수집 → 계약·부서 → 체크리스트 → 첫 출근 안내 | `onboarding_checklist_generator`, `new_employee_lookup`, `candidate_lookup` |

---

## 등록된 Skill

| skill_id | 타입 | 설명 |
|---|---|---|
| `translate` | LLM | 텍스트를 지정 언어로 번역 |
| `summarize` | LLM | 텍스트를 핵심 내용으로 요약 |
| `extract` | LLM | 핵심 키워드/항목 추출 |
| `calculator` | 툴 | 사칙연산 계산 |
| `vacation_parser` | LLM | 휴가 신청 정보(이름·기간·사유) 구조화 |
| `employee_lookup` | 툴 | 사내 직원 인사 정보 조회 (DUMMY_DB) |
| `jd_generator` | LLM | 직무·자격요건 → JD 마크다운 초안 |
| `resume_parser` | LLM | 자유 형식 이력서 → 구조화(학력·경력·스킬·자격증) |
| `jd_resume_match_score` | LLM | JD↔이력서 매칭 점수(0~100) + 적합·갭 사유 |
| `offer_letter_drafter` | LLM | 합격자 정보 → 공식 오퍼레터 본문 |
| `onboarding_checklist_generator` | LLM | 직무·직급 → 입사 1주차 체크리스트(5 카테고리) |
| `candidate_lookup` | 툴 | 후보자 ID(C-XXX) 조회 (DUMMY_DB) |
| `new_employee_lookup` | 툴 | 신규 입사자 ID(N-YYYY-XXX) 조회 (DUMMY_DB) |
| `chat` | 내장 | 일반 대화 / 종료 신호 |

---

## Supervisor 의사결정 흐름

매 턴 입력에 대해 Supervisor는 LLM 한 번 호출로 다음 4가지 중 하나를 선택합니다.

```
[입력]                                        [선택되는 action]
─────────────────────────────                 ─────────────────
"신규 채용하고 싶어"                       → switch_agent (recruitment_intake)
                                                · 사용자 확인 필요 시 user_confirm_needed=true
"포지션은 시니어 백엔드"  (agent active 중) → continue_agent
"12*8은?"                  (agent active 중) → call_skill (calculator), agent 유지
"안녕하세요"                                  → chat
```

- **세션 상태**: `active_agent`, `paused_agents`(스택), `pending_switch`(전환 승인 대기), `pending_skill`(슬롯 보충 대기), `global_state`, `history`.
- **Bubble-up**: agent가 범위 밖 요청을 감지하면 `next_action: "bubble_up"`으로 Supervisor에 반환 → 같은 턴 내 재진입(최대 1회).
- **Resume hint**: 단발 skill 실행 후 active_agent가 살아 있으면 "진행 중이던 X 업무를 이어서 진행할까요?" 안내 첨부 (config: `enable_resume_hint`).

---

## RAG 기반 Skill·Agent 검색

Skill·Agent가 늘어나도 토큰 초과 없이 관련 후보만 라우팅 컨텍스트에 주입합니다.

```
첫 실행:
  registry JSON 로드 → embedding=null인 항목만 Gemini Embedding API 호출
  (gemini-embedding-001, 3072차원) → registry JSON에 캐싱

매 요청:
  user_input → 임베딩 → 저장된 벡터들과 코사인 유사도 → Top-K 선택

폴백 체인:
  embedding 가용성 없음 → keyword 매칭 (trigger_keywords 부분일치)
  매칭 0건 → 전체 레지스트리 반환
```

`runner/retriever.py::Retriever`는 skill과 agent 양쪽에서 공유하는 제네릭 엔진입니다. 어댑터(`skill_retriever.py`, `agent_retriever.py`)는 도메인별 포맷팅 함수만 가지고 있습니다.

---

## Skill 실행 분기 (`components.py`)

```python
# 함수형 Skill: skills/tools/{skill_id}_tool.py 존재 시
tool_module.execute(params)        # Python 함수 직접 호출

# LLM Skill: tool 없으면
call_ai(system=worker_prompt, user=input)
```

**자가 치유 (Self-Healing):** 파라미터 JSON 파싱 실패 또는 함수 예외 발생 시, 에러 메시지를 LLM에 피드백으로 주입하고 최대 `max_iterations`회 재시도합니다.

---

## Slot Filling — 모호한 입력 대응

함수형 Skill이 모호한 입력("직원을 찾고 싶은데?")으로 임의 추출 → not_found 루프를 도는 문제를 4단계로 차단합니다.

1. **추출 프롬프트가 require_info 인지**: 구체적 식별자 없으면 `{"_status": "require_info", "ask_user": "..."}` 반환.
2. **components가 패스스루**: require_info JSON을 그대로 호출자에 전달.
3. **Supervisor `_format_skill_response`**: `_status=require_info` → `ask_user` 메시지 노출. `function_result.status=not_found` → message만 노출 (JSON 코드블록 X).
4. **Supervisor 단축회로 (`pending_skill`)**: require_info 시 세션에 `pending_skill` 세팅. 다음 턴 입력이 짧고(≤30자) 다른 agent 트리거가 없으면 LLM 결정 우회하고 `original_input + 신규 입력`으로 같은 skill 재호출. 취소어("그만", "아니야" 등) 감지 시 클리어. 다른 agent 트리거 감지 시 정상 라우팅.

```
USER: 직원을 찾고 싶은데?
AI:   어느 직원을 조회할까요? 이름을 알려주세요.
        ↑ pending_skill = {skill_id: employee_lookup, original_input: ...}

USER: 홍길동
        ↑ 단축회로: employee_lookup("직원을 찾고 싶은데? 홍길동")
AI:   결과: {dept: "영업팀", position: "대리", ...}
        ↑ pending_skill 클리어
```

---

## Judge / Refine 루프

LLM Skill 결과에만 적용되는 자가 평가·개선 사이클입니다.

```
judge_skill.md  → 출력 품질을 0~10점으로 채점
   score >= pass_threshold (기본: 7) → 통과
   score <  threshold        → refine_skill.md으로 피드백 기반 재생성
   max_iterations (기본: 3) 소진 → 강제 통과
```

---

## 설정 파일 (`prompts/loop_config.md`)

```
max_iterations: 3                # Judge/Refine 최대 반복
pass_threshold: 7                # Judge 통과 기준 (0~10)
force_exit_on_max: true          # 반복 한도 도달 시 강제 종료
context_window: last_2           # Refine 시 참조할 이전 피드백 수
temperature: 0                   # LLM 생성 온도
skill_retrieval_top_k: 3         # 라우팅에 제공할 Skill 후보 수
skill_retrieval_mode: embedding  # embedding | keyword | full
agent_retrieval_top_k: 3         # 라우팅에 제공할 Agent 후보 수
enable_resume_hint: true         # 단발 skill 후 agent 재개 안내 표시
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

### API 모드
```python
from runner.run import run

session = {}    # 빈 dict로 시작, 멀티턴 시 같은 객체를 계속 전달

result = run("휴직 신청하고 싶어요", session=session)
print(result["message"])     # AI 응답
session = result["session"]  # 갱신된 세션 (active_agent, history 등 포함)

result = run("김철수, 육아휴직입니다", session=session)
# leave_intake가 active 상태로 다음 단계 진행
```

**`run()` 반환값**:
```python
{
    "success": bool,
    "message": str,        # 사용자에게 보여줄 응답
    "session": dict,       # active_agent, paused_agents, pending_switch,
                           # pending_skill, global_state, history
}
```

---

## 새 Skill 추가

1. **`skills/worker_prompts/{skill_id}_skill.md`** — 추출/실행 프롬프트.
   - 함수형이면 파라미터 추출용 JSON.
   - LLM-only면 결과 자체를 JSON으로.
   - 모호한 입력 대응이 필요하면 `_status: require_info` 분기 포함.
2. **`skills/skill_registry.json`** — 항목 추가 (`embedding: null`, 다음 실행 시 자동 계산).
3. **(함수형이면) `skills/tools/{skill_id}_tool.py`** — `execute(params: dict) -> dict` 구현.

---

## 새 Agent 추가

1. **`agents/definitions/{agent_id}.md`** — 역할·workflow 단계·JSON I/O 스키마.
   - 출력 스키마: `{message, step_completed, collected, next_action, skill_call}`.
   - `next_action`: `ask_user` | `call_skill` | `done` | `bubble_up`.
2. **`agents/agent_registry.json`** — 메타데이터 + workflow 배열 + `allowed_skills` + `embedding: null`.
3. 다음 실행 시 자동으로 임베딩 캐싱 + Supervisor의 RAG 후보에 포함.

---

## 의존성

```bash
pip install openai google-genai python-dotenv
```

| 패키지 | 용도 |
|---|---|
| `openai` | Gemini API 호출 (OpenAI 호환 엔드포인트) |
| `google-genai` | Gemini Embedding API (`gemini-embedding-001`) |
| `python-dotenv` | `.env` 자동 로드 |

**API 키 설정**: `.env`의 `GEMINI_API_KEY` 또는 환경변수.

---

## 회귀 검증 시나리오

```bash
PYTHONIOENCODING=utf-8 python runner/run.py "1+1은?"
# → 결과: 2.0   (call_skill: calculator)

PYTHONIOENCODING=utf-8 python runner/run.py "안녕하세요"
# → 인사 응답   (chat)

PYTHONIOENCODING=utf-8 python runner/run.py "직원을 찾고 싶은데?"
# → "어느 직원을 조회할까요?"   (require_info → pending_skill 세팅)

PYTHONIOENCODING=utf-8 python runner/run.py "휴직 신청하고 싶어요"
# → "'휴직 접수' 업무로 시작할까요?"   (switch_agent confirm)

PYTHONIOENCODING=utf-8 python runner/run.py "신규 백엔드 개발자 채용하고 싶어요"
# → recruitment_intake 활성화, 첫 단계(요청자 정보) 질문
```
