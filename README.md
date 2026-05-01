# Skill Base AI

한국 기업 HR 담당자를 위한 **3계층 ReAct 에이전트** 시스템입니다.
Function calling을 지원하지 않는 자체 호스팅 모델(Gemma·Llama 등)에서도 동작하며, 다음 세 가지로 구성됩니다.

1. **도구 호출 (Phase 1)** — 한 응답에 여러 `<tool_call>`을 동시에 호출하고, 잘못된 인자는 모델이 스스로 교정
2. **Skill 카탈로그 (Phase 2)** — 33개 스킬을 7개 카테고리로 묶어 첫 턴엔 요약만, 필요할 때 펼쳐 사용 (context 80%+ 절감)
3. **워크플로우 서브에이전트 (Phase 3)** — 11개 HR 업무 워크플로우를 격리된 in-process 서브에이전트로 실행 (부모 컨텍스트 보호)

> **GitHub**: https://github.com/Mindh/SKILLAgent

---

## 빠른 시작

```bash
git clone https://github.com/Mindh/SKILLAgent.git
cd SKILLAgent
pip install -r requirements.txt

# API 키 설정 (둘 중 하나 — Google AI Studio용)
export GEMINI_API_KEY="AIzaSy..."
# 또는 runner/llm.py 상단의 GEMINI_API_KEY 값 직접 수정
# 자체 호스팅 모델을 쓰면 runner/llm.py만 교체하면 됨 (자세한 내용은 아래 "모델 교체" 절)

# 실행
python runner/run.py                     # CLI 대화형
python runner/run.py "1234 + 5678"       # CLI 단발 실행
python runner/web.py                     # 웹 UI (http://localhost:5000)
```

---

## 한눈에 보는 아키텍처

```
사용자 입력
   │
   ▼
┌──────────────────────────────────────────────────────────────┐
│              runner/loop.py — 부모 ReAct 루프                │
│                                                              │
│  ① 첫 턴: 카테고리 요약 주입 (1.3KB, 전체 schema X)          │
│  ② 워크플로우 매칭 검사 (키워드 → LLM 분류)                  │
│      ├ 매칭됨 → 서브에이전트 위임 (③로 점프)                 │
│      └ 없음   → 직접 처리 (④)                                │
│                                                              │
│  ③ 서브에이전트 활성화 (격리된 messages·자체 ReAct)          │
│      ├ 사용자 입력 → 서브에이전트로 라우팅                   │
│      ├ <workflow_complete> 태그 또는 max_turns로 종료         │
│      └ 부모엔 한 줄 요약만 흡수                              │
│                                                              │
│  ④ 다중 <tool_call> 추출 → 검증 → 실행 → 결과 주입 → 재호출  │
└──────────────────────────────────────────────────────────────┘
   │                    │                       │
   ▼                    ▼                       ▼
┌──────────┐    ┌──────────────┐    ┌──────────────────────┐
│ tools.py │    │ skill_loader │    │ workflow_retriever   │
│          │    │              │    │                      │
│ 도구     │    │ skills/      │    │ 키워드 매칭 (1차)    │
│ 디스패치 │←──│ <cat>/<name>/│    │ LLM 분류기 (2차)     │
│ 검증     │    │ SKILL.md     │    │ → frontmatter 로드   │
│ 메타도구 │    │              │    │                      │
│ list_    │    │ 33 skills /  │    │ 11 workflows         │
│ skills   │    │ 7 categories │    │                      │
└──────────┘    └──────────────┘    └──────────────────────┘
                                            │
                                            ▼
                                    ┌──────────────────────┐
                                    │  runner/subagent.py  │
                                    │  격리 ReAct 루프     │
                                    │  (자체 messages)     │
                                    └──────────────────────┘
```

---

## 1. 도구 호출 (Phase 1)

### `<tool_call>` 태그 + 다중 호출

모델은 응답 안에 다음 형식으로 도구를 호출합니다. **한 응답에 여러 블록**을 넣으면 동시에 실행됩니다.

```
연차 잔여와 출장비를 같이 알아볼게요.
<tool_call>
{"name": "leave_balance_calculator", "args": {"employee_name": "홍길동"}}
</tool_call>
<tool_call>
{"name": "expense_calculator", "args": {"destination": "부산", "days": 2, "transport": "ktx"}}
</tool_call>
```

### 호출 ID로 1:1 매핑

각 호출에 자동으로 `call_id`가 부여되어(`i1c1`, `i1c2`, …) 결과·오류 메시지가 정확히 매핑됩니다.

```
[도구 호출: leave_balance_calculator #i1c1]
[도구 실행 결과: leave_balance_calculator #i1c1] {"days_remaining": 12}
[도구 호출: expense_calculator #i1c2]
[도구 실행 결과: expense_calculator #i1c2] {"total_krw": 320000}
```

### 인자 검증 + 자동 재시도

호출 직전 `validate_args()`로 필수 파라미터를 확인합니다. 누락 시 모델에게 교정 피드백:

```
[도구 오류: jd_generator #i1c1]
필수 파라미터 누락 또는 비어 있음: job_title

위 오류를 참고해 올바른 인자로 다시 호출하거나, 사용자에게 추가 정보를 요청하세요.
```

### 파싱 견고성

다음 모두 인식합니다:
- `<tool_call>{...}</tool_call>` (권장)
- ` ```tool_call ... ``` ` (펜스 라벨)
- ` ```json ... ``` ` 안의 `{"name": ..., "args": ...}` 객체 (폴백)
- `arguments` ↔ `args` 키 자동 별칭
- 중첩 brace 안전 처리 (균형 매칭)

---

## 2. Skill 카탈로그 (Phase 2)

### 디렉터리 구조

```
skills/
├── hr_data/         (5개)  직원·후보자 조회, 휴가/출장비 계산
│   ├── employee_lookup/
│   │   ├── SKILL.md       ← 프론트매터 + 본문
│   │   └── tool.py        ← Python 실행 함수
│   └── ...
├── hr_text/         (5개)  번역·요약·휴가/이력서 파싱
│   └── translate/
│       ├── SKILL.md
│       └── prompt.md      ← LLM 도구 프롬프트
├── hr_writing/      (5개)  JD·오퍼레터·체크리스트·공지문
├── hr_eval/         (2개)  적합도·평가양식
├── hr_knowledge/    (3개)  노동법·매너·연봉
├── report/          (10개) 보고서·PPT 작성 10단계
└── misc/            (3개)  계산기·메일·포스터
```

### SKILL.md 프론트매터

```markdown
---
{
  "name": "employee_lookup",
  "category": "hr_data",
  "type": "python",
  "display_ko": "직원 정보 조회",
  "description": "직원 이름으로 사내 인사 정보를 조회합니다.",
  "trigger_keywords": ["직원", "사번 조회"],
  "parameters": {
    "type": "object",
    "properties": {
      "employee_name": {"type": "string", "description": "조회할 직원 이름"}
    },
    "required": ["employee_name"]
  }
}
---

# 직원 정보 조회

(본문 — 사용 가이드, 예시 등)
```

### 진보적 노출 (Progressive Disclosure)

전체 schema(7,100자)를 매번 컨텍스트에 욱여넣지 않고, 첫 턴엔 카테고리 요약(1,300자, **81% 절감**)만 보여줍니다:

```
[사용 가능한 도구 카테고리]
필요한 카테고리만 펼쳐 사용하세요. 상세는
<tool_call>{"name":"list_skills","args":{"category":"hr_writing"}}</tool_call>
로 호출.

### HR 데이터 조회·계산 (hr_data, 5개)
직원·후보자·신규 입사자 조회, 잔여 휴가/출장비 계산
포함 도구: candidate_lookup, employee_lookup, expense_calculator, leave_balance_calculator, new_employee_lookup

### HR 문서 작성 (hr_writing, 5개)
JD·오퍼레터·온보딩/퇴사 체크리스트·사내 공지 작성
포함 도구: announcement_writer, jd_generator, ...

(7개 카테고리 모두 표시)
```

모델이 처음 보는 카테고리의 도구를 쓰기 전에 `list_skills`로 펼쳐 schema를 확인합니다. 이미 잘 아는 도구(예: `calculator`)는 바로 호출해도 동작합니다 — 전체 schema는 항상 메모리에 있고, 단지 컨텍스트에 안 넣을 뿐.

---

## 3. 워크플로우 서브에이전트 (Phase 3)

### 부모 vs 서브에이전트 격리

기존엔 워크플로우 정의(.md 본문)를 부모 messages에 텍스트로 주입하고 같은 컨텍스트에서 진행했습니다. 이제는 **격리된 in-process 서브에이전트**가 자체 messages 리스트로 실행됩니다.

```
[부모 messages — 격리 후]
[1] user      "휴직 신청하고 싶어요"
[2] assistant [워크플로우 위임 시작: leave_intake]
[3] assistant 직원 이름과 휴직 사유를 알려주세요.        ← 서브에이전트가 생성
[4] user      "김철수, 육아휴직"
[5] assistant 받았습니다. 다음으로 ...                    ← 서브에이전트가 생성
[6] user      "네 진행해주세요"
[7] assistant 모든 절차 완료되었습니다.                   ← 서브에이전트가 생성 (태그 제거됨)
[8] user      [워크플로우 위임 종료: leave_intake | steps=3 | tools=2 | summary=김철수 육아휴직 접수 완료]

[서브에이전트 messages — 부모와 완전 분리]
[1] user      [도구 카테고리 + hr_data 자동 펼침]
[2] assistant 네, 절차와 도구를 확인했습니다.
[3] user      "휴직 신청하고 싶어요"
[4] assistant 직원 이름과 휴직 사유를 알려주세요.
[5] user      "김철수, 육아휴직"
[6] assistant [도구 호출: employee_lookup #s2c1]
[7] user      [도구 실행 결과: employee_lookup #s2c1] {...}
[8] assistant 받았습니다. 다음으로 ...
... (서브에이전트만 보유)
```

→ 부모 컨텍스트는 사용자 화면에 보이는 응답 + 짧은 위임 마커만 남음. 도구 호출·중간 추론은 모두 서브에이전트 안에서 처리되어 **부모 컨텍스트가 부풀지 않습니다**.

### 워크플로우 프론트매터

각 `agents/definitions/<id>.md`는 다음 메타데이터로 시작합니다:

```markdown
---
{
  "id": "leave_intake",
  "display_ko": "휴직 접수",
  "categories": ["hr_data"],     ← 서브에이전트 첫 턴에 자동 펼칠 카테고리
  "max_turns": 15,                ← 무한 루프 방지
  "mode": "dialog"                ← 다턴 대화형
}
---

# 휴직 접수 안내
... (절차 본문)
```

### 종료 신호

서브에이전트는 다음 중 하나로 종료됩니다:
- 응답에 `<workflow_complete>한 줄 요약</workflow_complete>` 태그 포함
- `max_turns` 도달 (안전장치)
- 사용자가 채팅 초기화

종료 시 부모 messages에는 한 줄 요약만 추가되고, `state['subagent_history']`에 audit trail(workflow_id, summary, step_count, tools_used)이 보존됩니다.

---

## 디렉터리 구조

```
Skill Base AI/
├── runner/                     # 실행 엔진
│   ├── run.py                  # 진입점 — run() API + interactive_loop()
│   ├── loop.py                 # 부모 ReAct 루프 — turn() 핵심 로직 + 서브에이전트 라우팅
│   ├── subagent.py             # 격리 in-process 서브에이전트 (Phase 3 신규)
│   ├── tools.py                # execute_tool, validate_args, list_skills 메타 도구
│   ├── skill_loader.py         # SKILL.md 카탈로그 로더 (Phase 2 신규)
│   ├── workflow_retriever.py   # 키워드 + LLM 분류기 + 프론트매터 로드
│   ├── llm.py                  # call_ai(system_prompt, user_prompt, temperature) — 시그니처 고정
│   ├── web.py                  # Flask + SSE 웹 UI
│   └── utils.py                # load_file, cached_file, log
│
├── skills/                     # 33개 스킬 (Phase 2 재편)
│   ├── hr_data/<name>/SKILL.md + tool.py    (5개)
│   ├── hr_text/<name>/SKILL.md + prompt.md  (5개)
│   ├── hr_writing/<name>/SKILL.md + ...     (5개)
│   ├── hr_eval/<name>/...                   (2개)
│   ├── hr_knowledge/<name>/...              (3개)
│   ├── report/<name>/...                    (10개)
│   └── misc/<name>/...                      (3개)
│
├── agents/                     # 11개 워크플로우
│   ├── agent_registry.json     # 키워드 + description (분류기용)
│   └── definitions/            # 프론트매터 + 본문 (Phase 3 갱신)
│       ├── leave_intake.md
│       ├── recruitment_intake.md
│       └── ... (총 11개)
│
├── prompts/
│   └── system_prompt.md        # 페르소나 + 도구 사용 규칙 + list_skills 가이드
│
└── scripts/                    # 1회용 마이그레이션 (Phase 2/3)
    ├── migrate_skills.py       # tools/ + worker_prompts/ → 카테고리 구조로 이동
    └── migrate_workflows.py    # 11개 .md에 프론트매터 삽입
```

---

## API 사용법

### `state` 기반 (권장 — Phase 3)

```python
from runner.run import run

state = {
    "messages": [],
    "injected_workflows": set(),
    "active_subagent": None,
    "subagent_history": [],
    "last_tool_events": [],
    "last_artifacts": [],
}

# Turn 1
res = run("휴직 신청하고 싶어요", state=state)
print(res["message"])
# → "직원 이름과 휴직 사유, 희망 시작일을 알려주세요."
print(state["active_subagent"]["workflow_id"])
# → "leave_intake"  (서브에이전트 활성화됨)

# Turn 2
res = run("김철수, 육아휴직, 2025-04-01", state=state)
print(res["message"])
# → "받았습니다. 다음으로 사유별 서류를 안내드릴게요."

# Turn 3 (서브에이전트가 종료 태그 출력)
res = run("진행해주세요", state=state)
print(state["active_subagent"])         # → None (종료됨)
print(state["subagent_history"])        # → [{"workflow_id":"leave_intake","summary":"...","step_count":3,"tools_used":["employee_lookup"]}]
```

### 레거시 시그니처 (백워드 호환)

```python
res = run("안녕하세요", messages=[], injected_workflows=set())
print(res["message"])
```

### `run()` 반환값

```python
{
    "success": bool,
    "message": str,                  # 사용자 노출 텍스트
    "messages": list,                # 부모 messages (in-place 갱신)
    "injected_workflows": set,       # (레거시 — Phase 3에선 사실상 미사용)
    "active_subagent": dict | None,  # 진행 중인 서브에이전트 상태
    "tool_events": list,             # 직전 턴의 도구 호출 이벤트
    "artifacts": list,               # 직전 턴에 회수된 HTML 등
    "subagent_history": list,        # 종료된 워크플로우 audit trail
}
```

---

## 웹 UI

```bash
python runner/web.py                     # 0.0.0.0:5000
python runner/web.py --port 8080
python runner/web.py --host 127.0.0.1
```

특징:
- **단계 스택** — 도구 호출·서브에이전트 위임을 접기·펼치기 가능한 카드로 표시 (기본은 접힘)
- **실시간 SSE** — `tool_call`/`tool_result`/`subagent_started`/`subagent_finished`/`ai_response` 이벤트
- **HTML 미리보기** — `<!DOCTYPE html>` 응답 자동 iframe 렌더링
- **메일 링크** — `mail_url_generator` 결과를 클릭 가능한 카드로
- **답변 칩** — AI 응답 후 사용자가 보낼 만한 답변 추측 (LLM 1회 추가)

운영 환경:
```bash
pip install gunicorn
gunicorn -b 0.0.0.0:5000 -w 1 --threads 4 runner.web:app
```
(SSE 특성상 worker 1 + threads N 권장)

---

## 모델 교체

LLM 호출은 모두 `runner/llm.py`의 **`call_ai()` 함수 하나**를 통해 수행됩니다. 다음 시그니처는 **절대 변경하지 마세요** — 변경하면 `loop.py` / `subagent.py` / 모든 LLM 도구가 깨집니다.

```python
def call_ai(system_prompt: str, user_prompt: str, temperature: float = 0) -> str:
    """반환: 모델 응답 텍스트 (실패 시 빈 문자열)"""
```

### 자체 호스팅 모델 (requests 기반 예시)

```python
# runner/llm.py
import os, time, requests
from runner.utils import log

MODEL_NAME = "my-self-hosted-model"

def call_ai(system_prompt: str, user_prompt: str, temperature: float = 0) -> str:
    start = time.time()
    try:
        r = requests.post(
            "http://my-model-server/v1/chat/completions",
            json={
                "model": MODEL_NAME,
                "messages": [
                    {"role": "user",
                     "content": f"[System Instructions]\n{system_prompt}\n\n[User Request]\n{user_prompt}"},
                ],
                "temperature": temperature,
            },
            timeout=60,
        )
        log(f"[LLM] API 응답: {time.time() - start:.2f}초")
        return r.json()["choices"][0]["message"]["content"] or ""
    except Exception as e:
        log(f"[LLM] API 호출 실패 - {e}")
        return ""
```

`openai` 패키지 없이 동작하며 Function calling·system role 미지원 모델(Gemma, Llama 등)도 그대로 사용 가능합니다.

> **Python 3.8 호환**: `typing.Optional`, `typing.List`만 사용하므로 3.8 이상에서 동작.

---

## 새 도구 추가

### Python 함수형

```bash
mkdir -p skills/<category>/<my_tool>
```

`skills/<category>/<my_tool>/tool.py`:
```python
def execute(params: dict):
    return {"result": "..."}
```

`skills/<category>/<my_tool>/SKILL.md`:
```markdown
---
{
  "name": "my_tool",
  "category": "<category>",
  "type": "python",
  "display_ko": "내 도구",
  "description": "도구 설명",
  "trigger_keywords": [],
  "parameters": {
    "type": "object",
    "properties": {"param1": {"type": "string", "description": "..."}},
    "required": ["param1"]
  }
}
---

# 내 도구

(본문)
```

→ 다음 실행부터 자동 등록. `runner/tools.py`나 `web.py` 수동 갱신 **불필요**.

### LLM 생성형

같은 디렉터리 구조에 `tool.py` 대신 `prompt.md`(LLM에 전달할 system prompt)를 두고 `SKILL.md`의 `type`을 `"llm"`으로 설정하면 끝.

---

## 새 워크플로우 추가

`agents/definitions/<my_workflow>.md`:
```markdown
---
{
  "id": "my_workflow",
  "display_ko": "내 워크플로우",
  "categories": ["hr_data", "hr_writing"],
  "max_turns": 15,
  "mode": "dialog"
}
---

# 내 워크플로우 안내

(절차·원칙 자유 작성)
```

`agents/agent_registry.json`에 항목 추가:
```json
{
  "agent_id": "my_workflow",
  "name": "내 워크플로우",
  "description": "워크플로우 설명 (LLM 분류기에 사용)",
  "trigger_keywords": ["키워드1", "키워드2"],
  "embedding": null
}
```

→ 다음 실행부터 키워드 매칭 → 서브에이전트 자동 위임으로 동작.

---

## 동작 검증 시나리오

```bash
# 일반 대화
python runner/run.py "안녕하세요"
# → 자연스러운 인사 + 다음 행동 제안

# 단일 도구
python runner/run.py "1234 더하기 5678"
# → calculator 호출 → "합계는 6912입니다."

# 다중 도구 동시 호출
python runner/run.py "홍길동 잔여 휴가랑 부산 2박 3일 출장비 같이 알려줘"
# → leave_balance_calculator + expense_calculator 동시 실행 → 종합 답변

# 슬롯 필링
python runner/run.py "직원 조회해줘"
# → 도구 호출 없이 "어느 직원을 조회할까요?" 질문

# 워크플로우 (서브에이전트 자동 위임)
python runner/run.py "휴직 신청하고 싶어요"
# → leave_intake 서브에이전트 시작 → 단계별 안내

# LLM 도구
python runner/run.py "이 문장을 영어로 번역해줘: 안녕하세요"
# → translate 호출 → "Hello."
```

---

## 마이그레이션 스크립트

기존(레거시 `skills/tools/`·`skills/worker_prompts/` + 프론트매터 없는 워크플로우 .md)에서 신규 구조로 이전할 때:

```bash
# Phase 2: skills/<category>/<name>/SKILL.md 구조로 이동
python scripts/migrate_skills.py --dry-run    # 계획 출력
python scripts/migrate_skills.py              # 실제 이동

# Phase 3: 11개 워크플로우 .md에 JSON 프론트매터 삽입 (멱등)
python scripts/migrate_workflows.py --dry-run
python scripts/migrate_workflows.py
```

---

## 의존성

```bash
pip install -r requirements.txt
```

| 패키지 | 필수 여부 | 용도 |
|---|---|---|
| `requests` | **필수** | 자체 호스팅 모델 호출 |
| `flask` | 웹 UI 사용 시 필수 | `runner/web.py` |
| `python-dotenv` | 선택 | `.env` 파일에서 API 키 자동 로드 |
| `openai` | 선택 | Google AI Studio 등 OpenAI 호환 엔드포인트를 쓸 때만 |

> **`loop.py` / `subagent.py`는 어떤 LLM SDK도 직접 import하지 않습니다.** 모든 LLM 호출은 `runner/llm.py`의 `call_ai()`를 통해 이루어지므로 `llm.py`만 자체 모델용으로 교체하면 됩니다.

---

## 핵심 파일 한눈에 보기

| 파일 | 역할 | 시그니처 변경 |
|---|---|---|
| `runner/llm.py` | LLM 호출 단일 진입점 | **금지** (자체 모델 환경에서 보호됨) |
| `runner/loop.py` | 부모 ReAct 루프 + 서브에이전트 라우팅 | 자유 |
| `runner/subagent.py` | 격리 in-process 서브에이전트 | 자유 |
| `runner/tools.py` | 도구 디스패치, `validate_args`, `list_skills` 메타 | 자유 |
| `runner/skill_loader.py` | SKILL.md 카탈로그 로더 | 자유 |
| `runner/workflow_retriever.py` | 워크플로우 매칭 + 프론트매터 로드 | 자유 |

---

## 한 줄 정리

> **부모 루프**가 일반 대화·단발 도구를 처리하고, **워크플로우는 서브에이전트로 격리**되어 부모 컨텍스트를 보호합니다. 도구는 **카테고리로 묶어 lazy 노출**하고, 한 응답에 **여러 호출을 동시에** 보낼 수 있으며, 잘못된 인자는 모델이 스스로 교정합니다. 모든 LLM 호출은 `runner/llm.py`의 `call_ai()` 하나만 거치므로 자체 호스팅 모델로 손쉽게 교체할 수 있습니다.
