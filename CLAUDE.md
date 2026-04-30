# CLAUDE.md — Skill Base AI 프로젝트 메모리

이 파일은 본 프로젝트와 관련해 협의·결정된 모든 사항을 섹션별로 정리한 메모리 문서입니다.
새 작업 시작 시 이 문서를 먼저 읽고 컨텍스트를 파악하세요.

---

## 1. 절대 제약 (Hard Constraints)

⚠️ **이 제약은 모든 작업에서 반드시 지킨다. 사용자가 명시적으로 풀어주기 전까지 위반 금지.**

| 제약 | 이유 |
|------|------|
| `runner/llm.py`의 `call_ai(system_prompt, user_prompt, temperature)` **시그니처 변경 금지** | 사용자가 자체 호스팅 모델 환경에서 이 파일을 직접 교체해 사용 중. 시그니처가 바뀌면 사용자 환경이 깨짐. |
| `openai` 라이브러리 **사용 금지** | 사용자 환경(Python 3.8, 자체 모델 서버)에서 openai 패키지 import 불가. `requests` 기반으로만 동작해야 함. |
| Python 3.8 호환 유지 | 사용자 서버가 3.8. PEP 585 generics(`list[X]`)·PEP 604 union(`X \| None`) 사용 금지. `typing.List`, `typing.Optional` 사용. |
| `agents/agent_registry.json`의 `embedding` 필드 무시 | 임베딩 검색 기능 제거됨. 기존 캐시 데이터는 그대로 두되 코드에서 참조 X. |
| `runner/llm.py` 자체는 `git pull` 시 사용자 서버에서 보호 (`skip-worktree` 또는 `merge=ours`) | 사용자 자체 모델 설정이 덮어써지지 않도록 |

---

## 2. 시스템 아키텍처

### 핵심 파일 구조

```
runner/
├── llm.py                  # ★ 변경 금지. call_ai(system_prompt, user_prompt, temperature) → str
├── loop.py                 # ReAct 루프. <tool_call> 태그 파싱 + 워크플로우 동적 주입
├── tools.py                # 33개 도구 정의 + execute_tool(name, args) + get_tool_descriptions()
├── workflow_retriever.py   # 키워드 매칭(1차) + LLM 분류기(2차)
├── run.py                  # CLI 진입점 + run() API
├── utils.py                # load_file, cached_file, log
└── web.py                  # Flask + SSE 웹 UI (단일 파일, 인라인 HTML/CSS/JS)

agents/
├── agent_registry.json     # 11개 워크플로우 메타데이터
└── definitions/*.md        # 11개 워크플로우 절차 정의 (자연어 + ReAct 형식)

skills/
├── tools/*_tool.py         # 7개 Python 함수형 도구 (정확한 동작)
└── worker_prompts/*.md     # 26개 LLM 도구 프롬프트 (AI 판단)

prompts/
└── system_prompt.md        # AI 페르소나 + 도구 사용 규칙 + 워크플로우 원칙
```

### 동작 흐름 (ReAct 루프)

```
사용자 입력
  ↓
loop.py::turn()
  ├── 첫 턴: 도구 목록 주입 (messages에 1회만)
  ├── workflow_retriever 호출 → 키워드 매칭(1차) → LLM 분류기(2차)
  │     workflow 매칭되면 컨텍스트 주입
  └── ReAct 루프 (최대 5회)
       ├── call_ai(system_prompt, serialized_messages) → 응답
       ├── 응답에서 <tool_call> 감지
       │     있으면 → execute_tool → 결과 messages에 주입 → 재호출
       │     없으면 → 최종 응답 반환
       └── 중간 응답은 [도구 호출: name] 요약으로 저장 (raw <tool_call> 안 남김)
```

### LLM 호출 인터페이스

```python
# runner/llm.py — 이 시그니처 절대 변경 금지
def call_ai(system_prompt: str, user_prompt: str, temperature: float = 0) -> str:
    ...
```

`loop.py`는 messages 리스트를 `_serialize_messages()`로 단일 문자열로 직렬화해 `user_prompt`에 전달.

---

## 3. 등록된 워크플로우 (11개)

| ID | 한글명 | 카테고리 |
|----|--------|---------|
| `leave_intake` | 휴직 접수 | HR 운영 |
| `vacation_request` | 연차/휴가 신청 | HR 운영 |
| `offboarding_intake` | 퇴사 접수 | HR 운영 |
| `recruitment_intake` | 채용 요청 접수 | 채용 |
| `onboarding_intake` | 온보딩 접수 | 채용 |
| `job_description_writing` | 직무기술서 작성 | 채용 |
| `business_trip_request` | 출장 신청 | 운영 |
| `performance_review` | 인사 평가 진행 | HR 운영 |
| `health_checkup_intake` | 건강검진 안내 | HR 운영 |
| `training_admission_intake` | 교육 입과 안내 | 교육 (HTML 포스터) |
| `report_writing` | 보고서·PPT 작성 | 보고서 (HTML 슬라이드) |

### 워크플로우 정의 작성 규칙

**현재 형식**: 자연어 + ReAct (`<tool_call>` 태그)
**구버전 형식 사용 금지**: `next_action`, `step_completed`, `collected`, `skill_call` 같은 JSON 강제 출력

워크플로우 .md에는 다음을 반드시 포함:
- 한 턴에 한 단계씩 진행
- **도구 호출 결과를 메시지에 반드시 포함** 후 후속 단계 진행 (결과 누락 금지)
- "시스템에 등록된 모든 도구를 자유롭게 사용 가능" 명시 (워크플로우 진행 중 다른 도구도 OK)

---

## 4. 등록된 도구 (33개)

### Python 함수형 (7개) — "정확한 동작"
```
calculator, employee_lookup, candidate_lookup, new_employee_lookup,
mail_url_generator, leave_balance_calculator, expense_calculator
```

### LLM 생성형 (26개) — "AI 판단"

**HR 일반 (12개)**:
```
translate, summarize, extract, vacation_parser, jd_generator, resume_parser,
jd_resume_match_score, offer_letter_drafter, onboarding_checklist_generator,
labor_law_qa, hr_etiquette, salary_advice
```

**HR 운영 도구 (3개)**:
```
offboarding_checklist_generator, announcement_writer,
performance_review_template_generator
```

**보고서·PPT 작성 (10개)**:
```
report_brief_analyzer, background_research, audience_analyzer,
key_message_extractor, storytelling_arc, report_outline_generator,
slide_content_enricher, data_visualization_recommender,
html_slide_deck_generator, speaker_notes_generator
```

**기타 (1개)**:
```
poster_html_generator (교육 포스터 HTML)
```

### 도구 추가 절차

1. Python 함수형: `skills/tools/{name}_tool.py` 생성 (`execute(params: dict)` 함수)
2. LLM 생성형: `skills/worker_prompts/{name}_skill.md` 생성
3. `runner/tools.py`의 `TOOL_DEFINITIONS`에 OpenAI 함수 형식으로 등록
4. Python 함수형이면 `_PYTHON_TOOLS` 집합에 이름 추가
5. `runner/web.py`의 `TOOL_DISPLAY_KO` 딕셔너리에 한글 표시명 추가

---

## 5. 웹 UI (`runner/web.py`) 핵심 결정사항

### 단일 파일 원칙
서버 라우트 + HTML/CSS/JS 모두 `runner/web.py` 하나에 인라인. 외부 정적 파일 X.

### 멀티 채팅 세션 관리
- 클라이언트 메모리(JS Map)만 사용 (localStorage·서버 영속성 X)
- 페이지 새로고침 = 새 시작 (요구사항)
- 서버 `SESSIONS`는 자동으로 session_id별 격리

### Server-Sent Events (SSE) 진행 표시
- 백그라운드 스레드에서 `loop.turn()` 실행
- 메인 스레드에서 messages 리스트 in-place 갱신을 polling
- 의미 있는 이벤트만 표시: `workflow_loaded`, `tool_call`, `tool_result`, `ai_response`
- 노이즈 단계는 spinner 뒤로 숨김

### UI 컴포넌트
- **사이드바**: `+ 새 채팅` (Pinterest Red), `📋 업무 프로세스 시작` (sand gray), 채팅 히스토리
- **헤더**: `🔧 도구·스킬 보기` 모달 + `현재 채팅 초기화`
- **업무 프로세스 모달**: `/workflows` endpoint에서 11개 목록 fetch, 검색·선택·시작
- **도구·스킬 모달**: `/tools` endpoint에서 33개 도구 + 11개 워크플로우 통합 표시
- **HTML 미리보기 카드**: AI 응답에 `<!DOCTYPE html>` 감지 → iframe sandbox 렌더링 + 다운로드/새 창
- **메일 링크 카드**: `mailto:` URL 감지 → 클릭 가능한 카드
- **후속 답변 칩**: AI 응답 후 사용자가 보낼 만한 답변 LLM 추측 (LLM 콜 1회 추가)

### 칩 클릭 동작
환영 화면의 예시 칩 클릭 시 입력창에 채우지 않고 **즉시 send()** 호출.

### AI 응답 후처리 (`_clean_ai_response`)
1. **HTML 감지** (`<!DOCTYPE html>` 또는 `<html>...</html>`) → 그대로 보존
2. **JSON 응답** → `message` 필드만 추출 (워크플로우의 `{message, step_completed, ...}` 형식 대응)
3. **코드블록** (` ```json ... ``` `) → 제거
4. **Reasoning 태그** (`<think>`, `<thought>`, `<thinking>`, `<reasoning>`, `<reflection>`, `<scratchpad>`) → 제거

### 워크플로우 매칭 로직
키워드 매칭(1차) → LLM 분류기(2차). 진행 중 워크플로우가 있으면 LLM 분류기 스킵 (`skip_llm_classify=True`) — 단답("네", "수정 없음")에 LLM 콜 낭비 방지.

---

## 6. Pinterest 디자인 시스템 (현재 적용된 테마)

### 색상 토큰
| 토큰 | 값 | 용도 |
|------|-----|------|
| `--bg` | `#ffffff` | warm white canvas |
| `--panel` | `#f6f6f3` | fog 표면 (카드·메시지) |
| `--panel-deep` | `#ebebe5` | sidebar 배경 |
| `--border` | `#e5e5e0` | sand gray 보더 |
| `--text` | `#211922` | plum black (절대 순수 검정 X) |
| `--text-soft` | `#62625b` | olive gray 보조 |
| `--muted` | `#91918c` | warm silver 비활성 |
| `--brand` | `#e60023` | Pinterest Red — CTA·전송 버튼만 |
| `--focus` | `#435ee5` | focus blue (입력 outline) |
| `--surface-sand` | `#e0e0d9` | 칩·secondary 버튼 |
| `--surface-warm` | `hsla(60, 20%, 98%, 0.7)` | warm wash 배경 |

### 타이포그래피
- 폰트: Pin Sans 폴백 체인 (proprietary라 시스템 폰트로 fallback)
- 한글: Apple SD Gothic Neo, Pretendard, Noto Sans KR
- `-webkit-font-smoothing: antialiased`

### 라운드 모서리
- 버튼·입력: **16px** (생성형 라운드, pill X)
- 카드: **16~20px**
- 모달: **28px**
- 아바타·원형 액션: **50%**

### 디자인 원칙
- 그림자 거의 없음 (flat by design, 깊이는 콘텐츠로)
- 그라데이션 지양 (단색 우선)
- 따뜻한 톤만 사용, 차가운 steel gray 일체 배제
- Pinterest Red는 **CTA 한 곳에만** 사용 (전송·새 채팅·확정 액션)

---

## 7. 시스템 프롬프트 (`prompts/system_prompt.md`) 페르소나

- **베테랑 HR 컨설턴트** (10년 이상 경력)
- 한국 노동법·인사·채용·보상·조직문화 전문
- 차분하고 전문적이지만 따뜻한 어조
- **응답 5원칙**: 결론 먼저 / 간결 / 구체적 / 솔직 / 한국 맥락
- Few-shot 예시 5개 포함 (인사·일반 질문·모호 요청·감사·도메인 외)

### 도구 사용 자율성
- 워크플로우 진행 중이어도 **모든 도구 자유 사용**
- "이 워크플로우는 X 도구만 쓴다"는 표현은 권장이지 금지가 아님

### 도구 결과 처리 원칙
- 도구 결과 받으면 **메시지에 반드시 포함** 후 후속 단계
- 여러 도구가 필요하면 **연속 호출** 후 종합 답변
- 결과 내용 없이 "다음 단계로 넘어갈게요"만 출력 금지

---

## 8. Git 운영 규칙

- **브랜치**: `claude/mystifying-hellman-b40807` (worktree)
- **커밋 메시지**: 한글, 변경 사유·범위 명시, 끝에 `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
- **푸시**: 사용자가 명시 요청 시에만 (`깃허브에 반영해줘` 류)
- **`.claude/settings.local.json`**: 절대 커밋 X (IDE 로컬 설정)
- **사용자 서버**: `runner/llm.py`는 `skip-worktree` 또는 `merge=ours`로 보호되므로 `git pull` 시 자동 보존

---

## 9. 스타일·UX 결정사항

### 채팅 UX
- **사용자가 자세히 알려주면**: 분석 도구 스킵하고 빠르게 진행
- **사용자가 대충 알려주면**: AI가 분석 도구 자동 호출해 정보 보강 (사용자에게 일일이 묻지 않음)
- **사회적 표현 빈도 낮춤**: "감사합니다" 같은 답변은 후속 답변 칩에서 1/3 이하만 (사용자는 보통 요청·명령형 답변을 함)

### HTML 출력
- AI가 HTML 결과(포스터·슬라이드)를 응답에 그대로 포함하면 자동 미리보기
- iframe sandbox로 안전 렌더링
- 다운로드·새 창 버튼 제공

### 일반 채팅
- 페르소나가 단순 인사 너머로 다음 행동 제안 ("HR 업무로 도와드릴 일 있으신가요?")
- 도메인 외 질문 (예: 점심 메뉴)은 자연스럽게 거절 + 본업 안내

---

## 10. 확장 시 우선 고려할 패턴

### 새 워크플로우 추가
1. `agents/definitions/{workflow_id}.md` — 자연어 + ReAct 형식
2. `agents/agent_registry.json` — entry 추가 (`embedding: null`)
3. `runner/web.py::WORKFLOW_DISPLAY_KO` — 한글명

### 새 도구 추가
1. Python: `skills/tools/{name}_tool.py` + `_PYTHON_TOOLS` 추가
2. LLM: `skills/worker_prompts/{name}_skill.md`
3. `runner/tools.py::TOOL_DEFINITIONS` 등록
4. `runner/web.py::TOOL_DISPLAY_KO` 한글명

### 새 UI 컴포넌트 추가
- `runner/web.py` 단일 파일 안에 CSS/JS 인라인
- Pinterest 토큰 사용 (`var(--brand)`, `var(--surface-sand)` 등)
- radius 16px 이상, 그림자 X, 따뜻한 톤만

### LLM 콜 최적화
- 단답·진행 중 워크플로우는 분류기 스킵
- 키워드로 해결 가능하면 LLM 콜 X
- 후속 답변 칩 같은 부가 기능은 사용자가 끌 수 있게 토글 옵션 검토 가능

---

**최종 업데이트**: 본 문서는 협의된 모든 결정사항의 누적 메모리입니다. 새로운 결정·변경은 해당 섹션에 추가하거나 갱신하세요.
