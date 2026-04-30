# -*- coding: utf-8 -*-
"""
Skill Base AI — 웹 UI (Flask + Server-Sent Events).

기존 runner/run.py::run()을 호출하면서, messages 리스트의 in-place 갱신을
백그라운드 스레드에서 polling해 진행 이벤트를 SSE로 실시간 푸시한다.

UI 표시 원칙:
  - 사용자에게 "최종 결정된 워크플로우/도구 1개"와 "결과"만 보여줌
  - 내부 분석 단계(분석 중·의도 감지 등)는 spinner 뒤로 숨김
  - 도구 호출/결과는 같은 카드 안에서 in-place 업데이트

사용법:
    python runner/web.py                    # 0.0.0.0:5000 (외부 접속 허용)
    python runner/web.py --port 8080
    python runner/web.py --host 127.0.0.1   # 로컬 전용
"""
import argparse
import json
import os
import sys
import threading
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, Response, jsonify, request

from runner.run import run

app = Flask(__name__)

# 단순 in-memory 세션 저장소 (단일 사용자/데모용)
SESSIONS: dict = {}

# 도구·워크플로우 한글 표시명 매핑 (UI 친화적 라벨)
TOOL_DISPLAY_KO = {
    "calculator": "계산기",
    "employee_lookup": "직원 정보 조회",
    "candidate_lookup": "후보자 정보 조회",
    "new_employee_lookup": "신규 입사자 정보 조회",
    "translate": "번역",
    "summarize": "요약",
    "extract": "키워드 추출",
    "vacation_parser": "휴가 정보 추출",
    "jd_generator": "채용공고 생성",
    "resume_parser": "이력서 분석",
    "jd_resume_match_score": "이력서 적합도 평가",
    "offer_letter_drafter": "오퍼레터 작성",
    "onboarding_checklist_generator": "온보딩 체크리스트 생성",
    "poster_html_generator": "교육 포스터 생성",
    "mail_url_generator": "메일 작성 링크 생성",
    "leave_balance_calculator": "잔여 휴가 계산",
    "expense_calculator": "출장비 견적",
    "offboarding_checklist_generator": "퇴사 체크리스트 생성",
    "announcement_writer": "사내 공지문 작성",
    "performance_review_template_generator": "평가 양식 생성",
    "labor_law_qa": "노동법 Q&A",
    "hr_etiquette": "직장 매너 조언",
    "salary_advice": "연봉/보상 조언",
    # 보고서·PPT 작성 도구
    "report_brief_analyzer": "보고서 의도 분석",
    "background_research": "배경·맥락 조사",
    "audience_analyzer": "청중 분석",
    "key_message_extractor": "핵심 메시지 추출",
    "storytelling_arc": "스토리 흐름 설계",
    "report_outline_generator": "보고서 개요 생성",
    "slide_content_enricher": "슬라이드 본문 보강",
    "data_visualization_recommender": "데이터 시각화 추천",
    "html_slide_deck_generator": "HTML 슬라이드덱 생성",
    "speaker_notes_generator": "발표 스크립트 작성",
}

WORKFLOW_DISPLAY_KO = {
    "leave_intake": "휴직 접수",
    "recruitment_intake": "채용 요청 접수",
    "onboarding_intake": "온보딩 접수",
    "job_description_writing": "직무기술서 작성",
    "training_admission_intake": "교육 입과 안내",
    "vacation_request": "연차/휴가 신청",
    "offboarding_intake": "퇴사 접수",
    "business_trip_request": "출장 신청",
    "performance_review": "인사 평가 진행",
    "health_checkup_intake": "건강검진 안내",
    "report_writing": "보고서·PPT 작성",
}


def _get_session(sid: str) -> dict:
    if sid not in SESSIONS:
        SESSIONS[sid] = {"messages": [], "injected_workflows": set()}
    return SESSIONS[sid]


def _classify_message(msg: dict):
    """
    messages 리스트의 항목을 UI 이벤트로 분류.
    None을 반환하면 UI에 표시되지 않음 (내부 단계).

    표시 대상 (의미 있는 이벤트):
      - workflow_loaded: 워크플로우가 결정·주입됨
      - tool_call:       도구 호출 시작
      - tool_result:     도구 결과 도착 (위 카드를 업데이트)
      - ai_response:     최종 AI 답변
    """
    role = msg.get("role", "")
    content = msg.get("content", "") or ""

    if role == "user" and content.startswith("[워크플로우 컨텍스트 로드:"):
        wf = content.split(":", 1)[1].split("]")[0].strip()
        display = WORKFLOW_DISPLAY_KO.get(wf, wf)
        return {
            "phase": "workflow_loaded",
            "text": f"'{display}' 워크플로우로 진행",
            "workflow_id": wf,
            "workflow_display": display,
        }

    if role == "assistant" and content.startswith("[도구 호출:"):
        name = content.replace("[도구 호출:", "").replace("]", "").strip()
        display = TOOL_DISPLAY_KO.get(name, name)
        return {
            "phase": "tool_call",
            "text": f"'{display}' 사용 중...",
            "tool_name": name,
            "tool_display": display,
        }

    if role == "user" and content.startswith("[도구 실행 결과:"):
        body = content.split("\n", 1)[1] if "\n" in content else ""
        result = body.split("\n\n위 결과를")[0].strip()
        name = content.split("\n", 1)[0].replace("[도구 실행 결과:", "").replace("]", "").strip()
        display = TOOL_DISPLAY_KO.get(name, name)

        # 도구별 특수 처리: 결과에서 클라이언트에 직접 노출할 정보 추출
        is_html = bool(_extract_html_block(result))
        mail_url = _extract_mail_url_from_result(result) if name == "mail_url_generator" else None

        if is_html:
            preview = "(HTML 포스터 생성 — 아래 미리보기 참고)"
        elif mail_url:
            preview = "(메일 작성 링크 생성 — 아래 링크 클릭)"
        else:
            preview = result[:500]

        return {
            "phase": "tool_result",
            "text": f"'{display}' 사용 완료",
            "tool_name": name,
            "tool_display": display,
            "result": preview,
            "mail_url": mail_url,
        }

    if role == "assistant" and not content.startswith("["):
        cleaned = _clean_ai_response(content)
        html = _extract_html_block(cleaned)
        if html:
            text_only = cleaned.replace(html, "").strip()
            return {
                "phase": "ai_response",
                "text": text_only or "포스터를 생성했습니다. 아래 미리보기를 확인해주세요.",
                "html": html,
            }
        return {"phase": "ai_response", "text": cleaned}

    # 그 외: 도구 목록 주입 / 일반 user 메시지 / assistant 확인 응답 — 모두 UI 표시 안 함
    return None


def _clean_ai_response(text: str) -> str:
    """
    AI 응답을 사용자에게 보여줄 자연어 메시지로 정제 (웹 UI 전용).

    일부 워크플로우(recruitment_intake 등)는 구조화된 JSON으로 응답한다:
        {"message": "...", "step_completed": null, "collected": {},
         "next_action": "ask_user", "skill_call": null}

    이 경우 `message` 필드만 추출해 사용자에게 보여준다.
    그 외 코드 블록은 제거한다.

    참고: 이 정제는 표시 목적만이며, messages 리스트에는 원본 JSON이 그대로
    저장되므로 다음 턴에서 AI가 이전 워크플로우 상태를 인식할 수 있다.
    """
    import re

    text = (text or "").strip()
    if not text:
        return text

    # ⓪-1. Reasoning 모델의 사고 과정 태그 제거
    # (DeepSeek R1: <think>, Qwen QwQ: <thought>, Claude: <thinking> 등)
    text = _strip_thinking_tags(text)

    # ⓪-2. 응답에 완전한 HTML 문서가 포함된 경우 → JSON 파싱·코드블록 제거 건너뜀 (HTML 보존)
    if _extract_html_block(text):
        return text

    # ① 응답 전체가 JSON 객체인 경우 → message 필드 추출
    if text.startswith("{") and text.endswith("}"):
        msg = _extract_message_from_json(text)
        if msg is not None:
            return msg

    # ② ```json ... ``` 코드블록 안에 JSON이 있는 경우 → message 필드 추출
    code_match = re.search(
        r"```(?:json|JSON)?\s*\n?(\{.*?\})\s*\n?```",
        text, re.DOTALL,
    )
    if code_match:
        msg = _extract_message_from_json(code_match.group(1))
        if msg is not None:
            return msg

    # ③ 일반 코드블록 제거 (system_prompt 규칙 어겼을 때 방어)
    cleaned = re.sub(
        r"```(?:json|JSON|javascript|js|python|py)?\s*\n?.*?\n?```",
        "", text, flags=re.DOTALL,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned if cleaned else text


# Reasoning(think) 모델이 출력에 포함하는 사고 과정 태그 목록
_THINKING_TAGS = (
    "thinking", "think", "thought", "thoughts",
    "reasoning", "reflection", "scratchpad",
)


def _strip_thinking_tags(text: str) -> str:
    """
    Reasoning 모델의 사고 과정 태그(<think>, <thought>, <thinking> 등)를 제거.
    여러 모델 패밀리(DeepSeek R1, Qwen QwQ, Claude extended thinking 등)가
    각기 다른 태그를 사용하므로 알려진 모든 패턴을 처리한다.
    """
    import re
    if not text:
        return text
    for tag in _THINKING_TAGS:
        text = re.sub(
            rf"<{tag}>.*?</{tag}>",
            "", text,
            flags=re.DOTALL | re.IGNORECASE,
        )
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _extract_mail_url_from_result(result_str: str):
    """도구 결과 문자열(JSON)에서 mail_url 필드 추출. 실패 시 None."""
    try:
        data = json.loads(result_str)
        if isinstance(data, dict):
            url = data.get("mail_url")
            if isinstance(url, str) and url.startswith("mailto:"):
                return url
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return None


def _extract_html_block(text: str) -> str:
    """텍스트에서 완전한 HTML 문서를 추출. 없으면 빈 문자열."""
    import re
    if not text:
        return ""
    # <!DOCTYPE html ...>로 시작해 </html>로 끝나는 블록, 또는 <html...>...</html>
    match = re.search(
        r"(<!DOCTYPE\s+html[^>]*>.*?</html>|<html[^>]*>.*?</html>)",
        text, re.DOTALL | re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _extract_message_from_json(json_str: str):
    """JSON 문자열에서 'message' 필드 추출. 실패 시 None."""
    try:
        data = json.loads(json_str)
        if isinstance(data, dict):
            msg = data.get("message")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return None


def _build_reply_suggestions(user_input: str, ai_text: str) -> list:
    """
    AI 응답을 분석해 사용자가 다음에 할 만한 짧은 답변 3개를 LLM이 추측 생성.

    - LLM 호출 1회 추가 발생 (짧은 응답 → 빠른 처리 기대)
    - 실패하면 빈 리스트 반환 (UI는 카드 미표시)
    - 워크플로우 진행 중이면 다음 단계에 어울리는 답변 (예: "김철수"),
      일반 대화면 후속 질문 (예: "자세히 알려줘")이 자연스러움
    """
    from runner.llm import call_ai

    if not ai_text or not ai_text.strip():
        return []

    system_prompt = (
        "당신은 사용자가 다음에 입력할 만한 짧은 답변을 추측하는 도우미입니다.\n"
        "방금 AI가 사용자에게 한 말을 보고, 사용자가 할 만한 답변 3개를 추측해 짧게 제시하세요.\n\n"
        "[응답 형식]\n"
        "오로지 JSON 배열 1줄만 출력. 각 항목은 5~25자 짧은 문장 (한국어).\n"
        "예: [\"다음 단계 알려줘\", \"홍길동 정보도 보여줘\", \"수정해줘\"]\n"
        "설명·코드블록·추가 텍스트 절대 금지.\n\n"
        "[추측 규칙]\n"
        "- 사용자는 보통 **AI에게 무언가 요청·명령**하거나 **정보를 제공**하는 형태로 답변합니다.\n"
        "- 좋은 예: \"다음 단계 알려줘\", \"홍길동도 확인해줘\", \"수정해줘\", \"다시 만들어줘\",\n"
        "           \"김철수입니다\", \"이걸로 진행\", \"다른 옵션 보여줘\"\n"
        "- 사회적 표현(\"감사합니다\", \"수고하세요\", \"잘 부탁드려요\")은 거의 사용하지 않으므로\n"
        "  3개 중 1개 이하로만 포함하세요.\n"
        "- AI가 정보를 물었으면 → 짧은 정답 또는 구체 예시 (이름·날짜·숫자 등)\n"
        "- AI가 작업을 마쳤으면 → 다음 요청형 (\"○○도 부탁해\", \"다른 거 만들어줘\", \"결과 다운로드 어떻게 해\")\n"
        "- AI가 선택을 요청하면 → 선택지 그대로 또는 \"다른 옵션 보여줘\", \"취소\"\n"
        "- 모든 칩은 짧고 자연스러운 한국어 (5~25자), 구체적이면서 행동 가능한 표현."
    )

    user_prompt = (
        f"[직전 사용자 메시지]\n{user_input}\n\n"
        f"[방금 AI 응답]\n{ai_text[:600]}\n\n"
        "→ 사용자가 다음에 보낼 만한 답변 3개를 JSON 배열로 출력하세요."
    )

    try:
        response = call_ai(system_prompt, user_prompt).strip()
    except Exception:
        return []

    # JSON 배열 추출 (모델이 코드블록·따옴표를 섞을 수 있으므로 방어적 파싱)
    import re
    # 코드블록 제거
    response = re.sub(r"```(?:json)?\s*\n?", "", response)
    response = re.sub(r"\n?```", "", response).strip()
    # 첫 번째 [...] 블록 추출
    match = re.search(r"\[.*?\]", response, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
        if not isinstance(data, list):
            return []
        # 문자열만 필터링, 길이 제한, 최대 3개
        items = [str(x).strip()[:30] for x in data if isinstance(x, str) and x.strip()][:3]
        return items
    except (json.JSONDecodeError, ValueError):
        return []


def _stream_events(user_input: str, sess: dict):
    """제너레이터: 진행 이벤트를 SSE 형식으로 yield."""

    def fmt(ev: dict) -> str:
        return f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    # 사전 분석 메시지를 별도로 푸시하지 않음 — 모든 결정은 loop.py 내부에서 발생,
    # web.py는 messages 리스트 변화만 관찰해 의미 있는 단계만 푸시.
    before_len = len(sess["messages"])
    result_holder: dict = {}
    error_holder: dict = {}

    def worker():
        try:
            result_holder["result"] = run(
                user_input,
                sess["messages"],
                sess["injected_workflows"],
            )
        except Exception as e:
            error_holder["error"] = str(e)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    def _enrich(ev: dict) -> dict:
        # ai_response 이벤트에 사용자 다음 답변 추측 첨부 (LLM 호출 1회 추가)
        if ev and ev.get("phase") == "ai_response":
            ev["suggestions"] = _build_reply_suggestions(user_input, ev.get("text") or "")
        return ev

    last_seen = before_len
    while thread.is_alive():
        time.sleep(0.05)
        cur_len = len(sess["messages"])
        if cur_len > last_seen:
            for i in range(last_seen, cur_len):
                ev = _classify_message(sess["messages"][i])
                if ev:
                    yield fmt(_enrich(ev))
            last_seen = cur_len

    thread.join()

    # 잔여 메시지 flush
    for i in range(last_seen, len(sess["messages"])):
        ev = _classify_message(sess["messages"][i])
        if ev:
            yield fmt(_enrich(ev))

    if error_holder:
        yield fmt({"phase": "error", "text": f"오류: {error_holder['error']}"})


# ── 라우트 ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return INDEX_HTML


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    sid = data.get("session_id", "default")
    user_input = (data.get("input") or "").strip()
    if not user_input:
        return jsonify({"error": "입력이 비어있습니다"}), 400

    sess = _get_session(sid)
    return Response(
        _stream_events(user_input, sess),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/reset", methods=["POST"])
def reset():
    data = request.get_json(silent=True) or {}
    sid = data.get("session_id", "default")
    SESSIONS.pop(sid, None)
    return jsonify({"ok": True})


@app.route("/tools")
def list_tools():
    """등록된 도구 목록 반환 (도구·스킬 확인 모달용)."""
    from runner.tools import TOOL_DEFINITIONS, _PYTHON_TOOLS
    items = []
    for tool in TOOL_DEFINITIONS:
        fn = tool["function"]
        name = fn["name"]
        items.append({
            "id": name,
            "name": TOOL_DISPLAY_KO.get(name, name),
            "description": fn.get("description", ""),
            "type": "python" if name in _PYTHON_TOOLS else "llm",
            "parameters": fn.get("parameters", {}).get("properties", {}),
            "required": fn.get("parameters", {}).get("required", []),
        })
    return jsonify(items)


@app.route("/workflows")
def list_workflows():
    """등록된 워크플로우 목록 반환 (모달 검색용)."""
    from runner.workflow_retriever import _load_registry
    registry = _load_registry()
    items = []
    for item in registry:
        wf_id = item["agent_id"]
        items.append({
            "id": wf_id,
            "name": WORKFLOW_DISPLAY_KO.get(wf_id, item.get("name", wf_id)),
            "description": item.get("description", ""),
            "keywords": item.get("trigger_keywords", []),
            # 자동 시작 메시지: 첫 키워드를 활용 (없으면 한글 이름)
            "start_phrase": (
                f"{item.get('trigger_keywords', [None])[0] or WORKFLOW_DISPLAY_KO.get(wf_id, wf_id)} "
                "진행 도와주세요"
            ),
        })
    return jsonify(items)


# ── 인라인 챗 UI ─────────────────────────────────────────────────────────────

INDEX_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Skill Base AI</title>
<style>
  :root {
    /* Pinterest-inspired warm light palette */
    --bg:           #ffffff;            /* Warm white canvas */
    --panel:        #f6f6f3;            /* Fog — light surface */
    --panel-deep:   #ebebe5;            /* Deeper fog for sidebar */
    --border:       #e5e5e0;            /* Sand gray border */
    --border-strong:#c8c8c1;            /* Stronger border */
    --text:         #211922;            /* Plum black — primary text */
    --text-soft:    #62625b;            /* Olive gray — secondary */
    --muted:        #91918c;            /* Warm silver — muted/disabled */
    --brand:        #e60023;            /* Pinterest Red — CTA only */
    --brand-hover:  #c70020;            /* Pressed red */
    --focus:        #435ee5;            /* Focus blue ring */

    /* Semantic accent (subtle warm tones, not bold) */
    --user:      #c2410c;               /* Warm orange-brown for user */
    --ai:        #211922;               /* Plum black for AI bubble */
    --tool:      #2b48d4;               /* Link blue for tool */
    --workflow:  #103c25;               /* Green 700 for workflow */
    --result:    #6845ab;               /* Performance purple for result */

    /* Surfaces with warm wash */
    --surface-warm: hsla(60, 20%, 98%, 0.7);
    --surface-sand: #e0e0d9;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    /* Pin Sans fallback chain (Pin Sans is proprietary; fallback handles all systems) */
    font-family: 'Pin Sans', -apple-system, system-ui, 'Segoe UI', Roboto,
                 'Apple SD Gothic Neo', 'Pretendard', 'Noto Sans KR',
                 ヒラギノ角ゴ Pro W3, メイリオ, Meiryo, 'Helvetica Neue',
                 Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text);
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  /* 좌-우 2분할 레이아웃 */
  .layout { display: flex; height: 100vh; }
  .sidebar {
    width: 240px; flex-shrink: 0;
    background: var(--panel-deep); border-right: 1px solid var(--border);
    display: flex; flex-direction: column;
    padding: 16px 12px; gap: 12px;
    overflow-y: auto;
  }
  .main-area {
    flex: 1; display: flex; flex-direction: column;
    min-width: 0;
  }
  #new-chat-btn, #workflow-chat-btn {
    border: none; padding: 10px 14px;
    border-radius: 16px; font-size: .9rem; font-weight: 700;
    cursor: pointer; text-align: left;
    transition: background-color .15s, transform .1s;
    font-family: inherit;
  }
  #new-chat-btn {
    background: var(--brand); color: #ffffff;
  }
  #new-chat-btn:hover { background: var(--brand-hover); }
  #workflow-chat-btn {
    background: var(--surface-sand); color: var(--text);
  }
  #workflow-chat-btn:hover { background: #d2d2cb; }

  /* ── 모달 ── */
  .modal-overlay {
    position: fixed; inset: 0;
    background: rgba(33, 25, 34, 0.45);
    display: none;
    z-index: 100;
    align-items: center; justify-content: center;
    backdrop-filter: blur(4px);
  }
  .modal-overlay.active { display: flex; }
  .modal {
    width: 90%; max-width: 600px; max-height: 80vh;
    background: #ffffff; border: 1px solid var(--border);
    border-radius: 28px;
    display: flex; flex-direction: column;
    overflow: hidden;
    animation: modalIn .25s ease-out;
  }
  @keyframes modalIn {
    from { opacity: 0; transform: scale(.95) translateY(10px); }
    to   { opacity: 1; transform: none; }
  }
  .modal-header {
    padding: 20px 24px; border-bottom: 1px solid var(--border);
    display: flex; justify-content: space-between; align-items: center;
  }
  .modal-header h2 {
    font-size: 1.15rem; font-weight: 700; color: var(--text);
    letter-spacing: -0.3px;
  }
  .modal-close {
    background: transparent; border: none; color: var(--text-soft);
    font-size: 1.6rem; cursor: pointer; padding: 0 6px;
    line-height: 1;
  }
  .modal-close:hover { color: var(--text); }

  .modal-search-wrap {
    padding: 14px 24px;
    border-bottom: 1px solid var(--border);
  }
  #wf-search-input, #tools-search-input {
    width: 100%; padding: 11px 15px;
    background: #ffffff; border: 1px solid var(--muted);
    border-radius: 16px; color: var(--text); font-size: .95rem;
    font-family: inherit;
    transition: border-color .15s, box-shadow .15s;
  }
  #wf-search-input:focus, #tools-search-input:focus {
    outline: none; border-color: var(--text);
    box-shadow: 0 0 0 3px rgba(67, 94, 229, 0.15);
  }
  #wf-search-input::placeholder, #tools-search-input::placeholder { color: var(--muted); }

  .modal-list {
    flex: 1; overflow-y: auto; padding: 12px 16px;
    display: flex; flex-direction: column; gap: 8px;
  }
  .wf-option {
    padding: 14px 16px; border-radius: 16px;
    border: 1px solid var(--border); background: #ffffff;
    cursor: pointer; transition: background-color .15s, border-color .15s;
  }
  .wf-option:hover {
    background: var(--surface-warm);
    border-color: var(--border-strong);
  }
  .wf-option.selected {
    background: #ffffff;
    border-color: var(--brand); border-width: 2px;
    padding: 13px 15px;
  }
  .wf-option .wf-name {
    font-size: 1rem; font-weight: 700; color: var(--text);
    margin-bottom: 4px;
  }
  .wf-option .wf-desc {
    font-size: .85rem; color: var(--text-soft); line-height: 1.5;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .wf-empty {
    text-align: center; color: var(--muted);
    padding: 40px 20px; font-size: .9rem;
  }

  .modal-footer {
    padding: 16px 24px; border-top: 1px solid var(--border);
    display: flex; justify-content: flex-end; gap: 8px;
  }
  #wf-start-btn {
    background: var(--brand); color: #ffffff;
    border: none; padding: 10px 20px;
    border-radius: 16px; font-size: .95rem; font-weight: 700;
    cursor: pointer; transition: background-color .15s;
    font-family: inherit;
  }
  #wf-start-btn:hover:not(:disabled) { background: var(--brand-hover); }
  #wf-start-btn:disabled { opacity: .35; cursor: not-allowed; }
  #wf-cancel-btn {
    background: var(--surface-sand); border: none;
    color: var(--text); padding: 10px 20px; border-radius: 16px;
    font-size: .95rem; font-weight: 600; cursor: pointer;
    transition: background-color .15s; font-family: inherit;
  }
  #wf-cancel-btn:hover { background: #d2d2cb; }
  .sidebar-label {
    font-size: .72rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: .05em;
    padding: 8px 12px 4px; font-weight: 700;
  }
  .chat-history {
    display: flex; flex-direction: column; gap: 2px;
    flex: 1; overflow-y: auto;
  }
  .chat-item {
    padding: 8px 12px; border-radius: 12px;
    font-size: .85rem; color: var(--text-soft); cursor: pointer;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    transition: background-color .15s, color .15s;
  }
  .chat-item:hover {
    background: var(--surface-warm);
    color: var(--text);
  }
  .chat-item.active {
    background: var(--surface-sand);
    color: var(--text); font-weight: 700;
  }

  /* 모바일: sidebar 숨김 */
  @media (max-width: 720px) {
    .sidebar { display: none; }
  }

  header {
    padding: 14px 24px; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between;
    background: rgba(255, 255, 255, 0.85); backdrop-filter: blur(8px);
    position: sticky; top: 0; z-index: 10;
  }
  header h1 {
    font-size: 1.15rem; font-weight: 700;
    color: var(--brand);
    letter-spacing: -0.3px;
  }
  .header-actions { display: flex; gap: 8px; }
  header button {
    background: var(--surface-sand); border: none;
    color: var(--text); padding: 6px 14px; border-radius: 16px;
    font-size: .82rem; font-weight: 600;
    cursor: pointer; transition: background-color .15s;
    font-family: inherit;
  }
  header button:hover { background: #d2d2cb; }

  /* ── 도구·스킬 모달 (워크플로우 모달과 같은 컴포넌트 + 약간 확장) ── */
  .modal-wide { max-width: 760px; }
  .tools-section-title {
    font-size: .8rem; font-weight: 700; color: var(--muted);
    text-transform: uppercase; letter-spacing: .05em;
    padding: 14px 8px 6px;
    position: sticky; top: 0;
    background: #ffffff; z-index: 1;
    color: var(--text-soft); font-weight: 700;
  }
  .tool-option {
    padding: 14px 16px; border-radius: 16px;
    border: 1px solid var(--border); background: #ffffff;
    transition: background-color .15s, border-color .15s;
  }
  .tool-option:hover {
    background: var(--surface-warm);
    border-color: var(--border-strong);
  }
  .tool-option .tool-name {
    font-size: 1rem; font-weight: 700; color: var(--text);
    display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  }
  .tool-option .tool-id {
    font-family: 'SF Mono', 'Consolas', monospace;
    font-size: .75rem; color: var(--muted);
  }
  .tool-type-badge {
    font-size: .7rem; font-weight: 700; padding: 3px 10px; border-radius: 12px;
  }
  /* "정확한 동작" — Pinterest sand 톤 */
  .tool-type-badge.python   { background: var(--surface-sand); color: var(--text); }
  /* "AI 판단" — performance purple 따뜻한 톤 */
  .tool-type-badge.llm      { background: hsla(280, 50%, 96%, 1); color: var(--result); }
  /* "워크플로우" — green 700 따뜻한 톤 */
  .tool-type-badge.workflow { background: hsla(150, 30%, 94%, 1); color: var(--workflow); }
  .tool-option .tool-desc {
    font-size: .85rem; color: var(--text-soft); margin-top: 6px; line-height: 1.5;
  }
  .tool-option .tool-params {
    margin-top: 10px; font-size: .76rem;
    background: var(--panel); border-radius: 12px; padding: 10px 12px;
    font-family: 'SF Mono', 'Consolas', monospace;
    color: var(--text-soft); line-height: 1.7;
    border: 1px solid var(--border);
  }
  .tool-option .tool-params .param-required {
    color: var(--brand); font-weight: 700;
  }

  #chat {
    flex: 1; overflow-y: auto;
    /* padding/max-width는 .chat-pane이 담당 (멀티 채팅 DOM 교체용) */
  }
  .chat-pane {
    /* createChat()에서 인라인으로도 설정. CSS에 명시적으로 정의 */
    padding: 24px;
    padding-bottom: 40px;
    max-width: 880px;
    width: 100%;
    margin: 0 auto;
  }

  .row { display: flex; margin-bottom: 16px; gap: 12px; }
  .row.user { justify-content: flex-end; }

  .avatar {
    width: 36px; height: 36px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.05rem; flex-shrink: 0;
    background: var(--surface-sand);
  }
  .row.ai .avatar { background: var(--surface-sand); color: var(--text); }
  .row.user .avatar {
    background: var(--brand); color: #ffffff; order: 2;
  }

  .ai-content {
    display: flex; flex-direction: column; max-width: 75%; gap: 8px;
  }

  .bubble {
    padding: 12px 16px; border-radius: 16px;
    line-height: 1.6; font-size: 1rem;
    white-space: pre-wrap; word-break: break-word;
  }
  .row.user .bubble {
    background: var(--brand); border: none;
    color: #ffffff; border-bottom-right-radius: 4px;
    max-width: 75%; font-weight: 500;
  }
  .row.ai .bubble {
    background: var(--panel); border: 1px solid var(--border);
    color: var(--text); border-bottom-left-radius: 4px;
  }

  /* 라이브 진행 표시 (단순 spinner, 모든 단계에서 동일 텍스트) */
  .live-progress {
    display: flex; align-items: center; gap: 10px; padding: 10px 14px;
    background: var(--surface-warm); border: 1px solid var(--border);
    border-radius: 16px; color: var(--text-soft); font-size: .88rem;
  }
  .spinner {
    width: 14px; height: 14px; border: 2px solid var(--border);
    border-top-color: var(--brand); border-radius: 50%;
    animation: spin .8s linear infinite; flex-shrink: 0;
  }
  .spinner-sm {
    width: 12px; height: 12px; border: 2px solid rgba(33, 25, 34, 0.15);
    border-top-color: currentColor; border-radius: 50%;
    animation: spin .8s linear infinite; flex-shrink: 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* 인라인 단계 카드 (워크플로우 / 도구) */
  .step-card {
    border-radius: 16px; padding: 12px 16px; font-size: .88rem;
    line-height: 1.4;
    animation: slideIn .25s ease-out;
  }
  @keyframes slideIn {
    from { opacity: 0; transform: translateX(-8px); }
    to { opacity: 1; transform: none; }
  }

  /* 워크플로우 진행 — 따뜻한 녹색 톤 (warm green) */
  .step-card.workflow {
    background: hsla(150, 30%, 96%, 1);
    border: 1px solid hsla(150, 25%, 80%, 1);
    color: var(--workflow);
    display: flex; align-items: center; gap: 8px;
    font-weight: 500;
  }

  /* 도구 진행 — 따뜻한 보라/베이지 톤 */
  .step-card.tool {
    background: var(--surface-warm);
    border: 1px solid var(--border);
    color: var(--text-soft);
    display: flex; flex-direction: column; gap: 8px;
    font-weight: 500;
  }
  .step-card.tool.done {
    background: hsla(280, 25%, 97%, 1);
    border-color: hsla(280, 20%, 85%, 1);
    color: var(--result);
  }
  .step-card.tool .header-line {
    display: flex; align-items: center; gap: 8px;
  }
  .step-card.tool .result-body {
    background: #fafafa; border-radius: 12px; padding: 10px 12px;
    font-family: 'SF Mono', 'Consolas', 'Fira Code', monospace; font-size: .78rem;
    color: var(--text-soft); white-space: pre-wrap; word-break: break-all;
    max-height: 200px; overflow-y: auto;
    border: 1px solid var(--border);
  }

  .typing-cursor {
    display: inline-block; width: 2px; height: 1em;
    background: var(--brand); margin-left: 2px;
    animation: blink 1s step-end infinite; vertical-align: text-bottom;
  }
  @keyframes blink { 50% { opacity: 0; } }

  /* HTML 미리보기 카드 — 채팅 버블 너비에 맞게 자동 축소 */
  .html-preview {
    border: 1px solid var(--border); border-radius: 20px;
    overflow: hidden; background: #ffffff;
    animation: slideIn .25s ease-out;
  }
  .preview-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 16px; background: var(--panel);
    color: var(--text);
    font-size: .85rem; border-bottom: 1px solid var(--border);
    font-weight: 600;
  }
  .preview-actions { display: flex; gap: 6px; }
  .preview-btn {
    background: var(--surface-sand); border: none; color: var(--text);
    padding: 6px 14px; border-radius: 16px; font-size: .78rem;
    cursor: pointer; font-weight: 700;
    transition: background-color .15s;
    font-family: inherit;
  }
  .preview-btn:hover { background: #d2d2cb; }
  .iframe-wrap {
    width: 100%; overflow: hidden;
    position: relative; background: white;
  }
  .html-preview iframe {
    width: 800px; height: 1100px;
    border: none; display: block;
    transform-origin: top left;
    background: white;
  }

  /* 후속 제안 — 사용자가 다음에 보낼 만한 짧은 답변 칩 */
  .suggestions {
    margin-top: 8px; display: flex; flex-direction: column; gap: 8px;
    animation: slideIn .3s ease-out;
  }
  .suggestions-label {
    font-size: .72rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: .05em; font-weight: 700;
    padding-left: 4px;
  }
  .suggestions-row {
    display: flex; gap: 8px; flex-wrap: wrap;
  }
  .reply-chip {
    background: var(--surface-sand);
    border: none;
    color: var(--text);
    font-size: .88rem; font-weight: 500;
    padding: 8px 16px;
    border-radius: 16px;
    cursor: pointer;
    transition: background-color .15s, transform .1s;
    font-family: inherit;
    line-height: 1.3;
  }
  .reply-chip:hover {
    background: #d2d2cb; transform: translateY(-1px);
  }

  /* 메일 링크 카드 */
  .mail-link-card {
    background: var(--surface-warm);
    border: 1px solid var(--border);
    border-radius: 16px; padding: 14px 16px; font-size: .9rem;
    display: flex; align-items: center; gap: 10px;
    color: var(--text);
  }
  .mail-link-card a {
    background: var(--brand); color: #ffffff; text-decoration: none;
    padding: 8px 16px; border-radius: 16px; font-size: .82rem;
    font-weight: 700; margin-left: auto;
    transition: background-color .15s;
  }
  .mail-link-card a:hover { background: var(--brand-hover); }

  /* 입력창 */
  footer {
    padding: 16px 24px; border-top: 1px solid var(--border);
    background: var(--bg);
  }
  .input-wrap {
    max-width: 880px; margin: 0 auto;
    display: flex; gap: 10px; align-items: flex-end;
  }
  textarea {
    flex: 1; resize: none; padding: 11px 16px; min-height: 48px; max-height: 160px;
    background: #ffffff; border: 1px solid var(--muted);
    border-radius: 16px; color: var(--text); font-size: 1rem;
    font-family: inherit; line-height: 1.5;
    transition: border-color .15s, box-shadow .15s;
  }
  textarea:focus {
    outline: none; border-color: var(--text);
    box-shadow: 0 0 0 3px rgba(67, 94, 229, 0.15);
  }
  textarea::placeholder { color: var(--muted); }
  #send {
    padding: 12px 24px; background: var(--brand);
    color: #ffffff; border: none; border-radius: 16px;
    font-size: 1rem; font-weight: 700; cursor: pointer;
    transition: background-color .15s, transform .1s;
    font-family: inherit;
  }
  #send:hover:not(:disabled) { background: var(--brand-hover); transform: translateY(-1px); }
  #send:disabled { opacity: .4; cursor: not-allowed; }

  .hint {
    text-align: center; padding: 48px 16px; color: var(--text-soft);
    font-size: 1rem;
  }
  .hint .examples {
    display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;
    margin-top: 20px;
  }
  .example-chip {
    background: var(--surface-sand); border: none;
    color: var(--text); font-weight: 500;
    padding: 8px 16px; border-radius: 16px; font-size: .85rem;
    cursor: pointer; transition: background-color .15s;
    font-family: inherit;
  }
  .example-chip:hover { background: #d2d2cb; }
</style>
</head>
<body>

<div class="layout">
  <aside class="sidebar">
    <button id="new-chat-btn">+ 새 채팅</button>
    <button id="workflow-chat-btn">📋 업무 프로세스 시작</button>
    <div class="sidebar-label">최근 대화</div>
    <div class="chat-history" id="chat-history"></div>
  </aside>

  <main class="main-area">
    <header>
      <h1>🤖 Skill Base AI</h1>
      <div class="header-actions">
        <button id="tools-btn">🔧 도구·스킬 보기</button>
        <button id="reset">현재 채팅 초기화</button>
      </div>
    </header>

    <div id="chat"></div>

    <footer>
      <div class="input-wrap">
        <textarea id="input" placeholder="메시지를 입력하세요... (Shift+Enter: 줄바꿈, Enter: 전송)"></textarea>
        <button id="send">전송</button>
      </div>
    </footer>
  </main>
</div>

<!-- 업무 프로세스 선택 모달 -->
<div class="modal-overlay" id="wf-modal">
  <div class="modal" role="dialog" aria-labelledby="wf-modal-title">
    <div class="modal-header">
      <h2 id="wf-modal-title">📋 업무 프로세스 선택</h2>
      <button class="modal-close" id="wf-close-btn" aria-label="닫기">×</button>
    </div>
    <div class="modal-search-wrap">
      <input type="text" id="wf-search-input"
             placeholder="이름·키워드로 검색 (예: 휴직, 채용, 출장)"
             autocomplete="off">
    </div>
    <div class="modal-list" id="wf-list">
      <div class="wf-empty">목록을 불러오는 중...</div>
    </div>
    <div class="modal-footer">
      <button id="wf-cancel-btn">취소</button>
      <button id="wf-start-btn" disabled>채팅 시작</button>
    </div>
  </div>
</div>

<!-- 도구·스킬 확인 모달 -->
<div class="modal-overlay" id="tools-modal">
  <div class="modal modal-wide" role="dialog" aria-labelledby="tools-modal-title">
    <div class="modal-header">
      <h2 id="tools-modal-title">🔧 사용 가능한 도구·스킬</h2>
      <button class="modal-close" id="tools-close-btn" aria-label="닫기">×</button>
    </div>
    <div class="modal-search-wrap">
      <input type="text" id="tools-search-input"
             placeholder="이름·설명·키워드로 검색..."
             autocomplete="off">
    </div>
    <div class="modal-list" id="tools-list">
      <div class="wf-empty">로드 중...</div>
    </div>
  </div>
</div>

<script>
// ── 멀티 채팅 상태 관리 ───────────────────────────────────────────────────
const chats = new Map();   // chatId → { title, dom, sessionId }
let activeChatId = null;

const $chat = document.getElementById("chat");
const $input = document.getElementById("input");
const $send = document.getElementById("send");
const $reset = document.getElementById("reset");
const $newChatBtn = document.getElementById("new-chat-btn");
const $chatHistory = document.getElementById("chat-history");

// 환영 HTML — 새 채팅 생성 시마다 삽입
const WELCOME_HTML = `
  <div class="hint" data-role="welcome">
    안녕하세요! HR 업무를 도와드립니다.
    <div class="examples">
      <span class="example-chip" data-text="안녕하세요!">안녕하세요!</span>
      <span class="example-chip" data-text="1234 더하기 5678 계산해줘">1234 더하기 5678 계산해줘</span>
      <span class="example-chip" data-text="홍길동 직원 정보 알려줘">홍길동 직원 정보 알려줘</span>
      <span class="example-chip" data-text="휴직 신청하고 싶어요">휴직 신청하고 싶어요</span>
      <span class="example-chip" data-text="김철수 연차 신청">연차 신청 (김철수)</span>
      <span class="example-chip" data-text="박민수 퇴사 접수해줘">퇴사 접수 (박민수)</span>
      <span class="example-chip" data-text="부산으로 2일 출장 신청">출장 신청 (부산 2일)</span>
      <span class="example-chip" data-text="신입사원 OJT 교육 안내 포스터 만들어줘">교육 포스터 만들어줘</span>
      <span class="example-chip" data-text="대리 자기평가 양식 만들어줘">평가 양식 (대리 자기평가)</span>
      <span class="example-chip" data-text="1분기 사업 성과 보고서 PPT 만들어줘">보고서·PPT 작성</span>
      <span class="example-chip" data-text="안녕을 영어로 번역해줘">번역</span>
    </div>
  </div>
`;

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => (
    {'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]
  ));
}

function bindChipsInScope(scopeDom) {
  // 환영 메시지 안의 칩 클릭 시 즉시 send()
  scopeDom.querySelectorAll(".example-chip").forEach(el => {
    el.addEventListener("click", () => {
      $input.value = el.dataset.text;
      send();
    });
  });
}

function createChat() {
  const id = "chat_" + Date.now() + "_" + Math.random().toString(36).slice(2, 6);
  const dom = document.createElement("div");
  dom.className = "chat-pane";
  dom.style.cssText = "padding:24px; max-width:880px; width:100%; margin:0 auto;";
  dom.innerHTML = WELCOME_HTML;
  bindChipsInScope(dom);
  chats.set(id, { title: "새 채팅", dom, sessionId: id });
  return id;
}

function switchChat(id) {
  if (activeChatId === id) return;
  $chat.innerHTML = "";
  const chat = chats.get(id);
  if (!chat) return;
  $chat.appendChild(chat.dom);
  activeChatId = id;
  renderHistory();
  scrollChatToBottom();
  $input.focus();
}

function renderHistory() {
  $chatHistory.innerHTML = "";
  // 최근 채팅이 위에 오도록 역순
  const ids = Array.from(chats.keys()).reverse();
  for (const id of ids) {
    const chat = chats.get(id);
    const item = document.createElement("div");
    item.className = "chat-item" + (id === activeChatId ? " active" : "");
    item.textContent = chat.title;
    item.dataset.chatId = id;
    item.title = chat.title;
    item.addEventListener("click", () => switchChat(id));
    $chatHistory.appendChild(item);
  }
}

function updateChatTitle(id, text) {
  const chat = chats.get(id);
  if (!chat) return;
  if (chat.title === "새 채팅" && text) {
    chat.title = text.slice(0, 30) + (text.length > 30 ? "..." : "");
    renderHistory();
  }
}

function scrollChatToBottom() {
  $chat.scrollTop = $chat.scrollHeight;
}
// 기존 코드 호환용 alias
const scrollToBottom = scrollChatToBottom;

function removeWelcome(chatDom) {
  const welcome = chatDom.querySelector('[data-role="welcome"]');
  if (welcome) welcome.remove();
}

function addUserBubble(chatDom, text) {
  removeWelcome(chatDom);
  const row = document.createElement("div");
  row.className = "row user";
  row.innerHTML = `
    <div class="bubble">${escapeHtml(text)}</div>
    <div class="avatar">👤</div>
  `;
  chatDom.appendChild(row);
  scrollChatToBottom();
}

function addAIContainer(chatDom) {
  const row = document.createElement("div");
  row.className = "row ai";
  row.innerHTML = `
    <div class="avatar">🤖</div>
    <div class="ai-content">
      <div class="live-progress" data-role="live">
        <div class="spinner"></div>
        <span>처리 중...</span>
      </div>
    </div>
  `;
  chatDom.appendChild(row);
  scrollChatToBottom();
  return row;
}

// tool_call → tool_result 카드 통합용 맵
function appendStepCard(aiRow, ev, ctx) {
  const content = aiRow.querySelector('.ai-content');
  const live = content.querySelector('[data-role="live"]');

  if (ev.phase === "workflow_loaded") {
    const display = ev.workflow_display || ev.workflow_id || "";
    const card = document.createElement("div");
    card.className = "step-card workflow";
    card.innerHTML = `<span>📋</span> <span>${escapeHtml(ev.text)}</span>`;
    content.insertBefore(card, live);
    scrollToBottom();
  }
  else if (ev.phase === "tool_call") {
    const display = ev.tool_display || ev.tool_name;
    const card = document.createElement("div");
    card.className = "step-card tool";
    card.innerHTML = `
      <div class="header-line">
        <div class="spinner-sm"></div>
        <span>🔧 '${escapeHtml(display)}' 사용 중...</span>
      </div>
    `;
    ctx.activeTools[ev.tool_name] = card;
    content.insertBefore(card, live);
    scrollToBottom();
  }
  else if (ev.phase === "tool_result") {
    const display = ev.tool_display || ev.tool_name;
    const card = ctx.activeTools[ev.tool_name];
    if (card) {
      card.classList.add("done");
      card.querySelector(".header-line").innerHTML = `
        <span>✅</span>
        <span>'${escapeHtml(display)}' 사용 완료</span>
      `;
      const result = (ev.result || "").trim();
      if (result) {
        const body = document.createElement("div");
        body.className = "result-body";
        body.textContent = result;
        card.appendChild(body);
      }
      // 메일 링크 도구 결과면 클릭 가능 링크 버튼 추가
      if (ev.mail_url) {
        const linkRow = document.createElement("div");
        linkRow.style.cssText = "display:flex; gap:8px; margin-top:6px;";
        const linkBtn = document.createElement("a");
        linkBtn.href = ev.mail_url;
        linkBtn.target = "_blank";
        linkBtn.rel = "noopener";
        linkBtn.className = "preview-btn";
        linkBtn.style.cssText = "background:var(--brand); text-decoration:none; padding:8px 16px; border-radius:16px; color:#ffffff; font-size:.82rem; font-weight:700; display:inline-block;";
        linkBtn.textContent = "✉️ 메일 작성 화면 열기";
        linkRow.appendChild(linkBtn);
        card.appendChild(linkRow);
      }
      delete ctx.activeTools[ev.tool_name];
      scrollToBottom();
    }
  }
  // 그 외 phase는 카드 추가 X (spinner만 유지)
}

// AI 응답에서 mailto: URL을 추출해 클릭 가능한 링크로 표시
function extractMailtoUrl(text) {
  const match = (text || "").match(/(mailto:[^\\s<>"]+)/i);
  return match ? match[1] : "";
}

// iframe을 컨테이너 너비에 맞게 transform: scale로 축소
function fitIframeToContainer(previewCard, baseWidth, baseHeight) {
  const wrap = previewCard.querySelector('.iframe-wrap');
  const iframe = previewCard.querySelector('iframe');
  if (!wrap || !iframe) return;
  const containerWidth = wrap.clientWidth;
  if (containerWidth <= 0) return;
  const scale = Math.min(containerWidth / baseWidth, 1);  // 축소만, 확대는 X
  iframe.style.transform = `scale(${scale})`;
  wrap.style.height = (baseHeight * scale) + 'px';
}

function appendSuggestions(content, suggestions) {
  if (!suggestions || !suggestions.length) return;

  const wrap = document.createElement("div");
  wrap.className = "suggestions";
  wrap.innerHTML = `<div class="suggestions-label">💡 이렇게 답해보세요</div>`;

  const row = document.createElement("div");
  row.className = "suggestions-row";

  for (const text of suggestions) {
    if (typeof text !== "string" || !text.trim()) continue;
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "reply-chip";
    chip.textContent = text;
    chip.addEventListener("click", () => {
      $input.value = text;
      send();
    });
    row.appendChild(chip);
  }

  if (!row.children.length) return;   // 유효한 칩이 없으면 미표시
  wrap.appendChild(row);
  content.appendChild(wrap);
  scrollChatToBottom();
}

function finalizeAI(aiRow, finalText, finalHtml, suggestions) {
  const content = aiRow.querySelector('.ai-content');
  const live = content.querySelector('[data-role="live"]');
  if (live) live.remove();

  // ① 텍스트 버블 (있을 때만)
  if (finalText && finalText.trim()) {
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = '<span data-role="text"></span><span class="typing-cursor"></span>';
    content.appendChild(bubble);
    typewriter(bubble.querySelector('[data-role="text"]'), finalText, () => {
      const cursor = bubble.querySelector(".typing-cursor");
      if (cursor) cursor.remove();
    });

    // 텍스트 안에 mailto: 링크가 있으면 별도 카드로 강조
    const mailUrl = extractMailtoUrl(finalText);
    if (mailUrl) {
      const mailCard = document.createElement("div");
      mailCard.className = "mail-link-card";
      mailCard.innerHTML = `
        <span>✉️</span>
        <span>메일 작성 링크가 준비됐습니다</span>
        <a href="${escapeHtml(mailUrl)}" target="_blank">메일 작성 화면 열기</a>
      `;
      content.appendChild(mailCard);
    }
  }

  // ② HTML 미리보기 (있을 때만) — 채팅 버블 너비에 맞춰 자동 축소
  if (finalHtml) {
    const previewCard = document.createElement("div");
    previewCard.className = "html-preview";
    previewCard.innerHTML = `
      <div class="preview-header">
        <span>📄 HTML 미리보기</span>
        <div class="preview-actions">
          <button class="preview-btn" data-action="open">새 창 열기</button>
          <button class="preview-btn" data-action="download">다운로드</button>
        </div>
      </div>
      <div class="iframe-wrap">
        <iframe sandbox="allow-same-origin" srcdoc=""></iframe>
      </div>
    `;
    const iframe = previewCard.querySelector("iframe");
    iframe.srcdoc = finalHtml;

    previewCard.querySelector('[data-action="open"]').addEventListener("click", () => {
      const blob = new Blob([finalHtml], { type: "text/html;charset=utf-8" });
      window.open(URL.createObjectURL(blob), "_blank");
    });
    previewCard.querySelector('[data-action="download"]').addEventListener("click", () => {
      const blob = new Blob([finalHtml], { type: "text/html;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "poster.html";
      a.click();
    });

    content.appendChild(previewCard);

    // iframe을 컨테이너 너비에 맞게 자동 축소 (포스터 800x1100 기준)
    fitIframeToContainer(previewCard, 800, 1100);
    // window resize 시 재계산 (한 번만 등록)
    window.addEventListener("resize", () => fitIframeToContainer(previewCard, 800, 1100));

    scrollToBottom();
  }

  // 둘 다 없으면 빈 응답 표시
  if (!finalText && !finalHtml) {
    const empty = document.createElement("div");
    empty.className = "bubble";
    empty.style.color = "var(--muted)";
    empty.textContent = "(빈 응답)";
    content.appendChild(empty);
  }

  // 후속 제안 카드 (있을 때만)
  appendSuggestions(content, suggestions);
}

function typewriter(el, text, onDone) {
  let i = 0;
  const speed = 12;
  function tick() {
    if (i >= text.length) {
      if (onDone) onDone();
      return;
    }
    const chunk = text.slice(i, i + 2);
    el.textContent += chunk;
    i += 2;
    scrollToBottom();
    setTimeout(tick, speed);
  }
  tick();
}

async function send() {
  const text = $input.value.trim();
  if (!text) return;

  // 활성 채팅의 DOM과 session_id 가져오기
  const chat = chats.get(activeChatId);
  if (!chat) return;
  const chatDom = chat.dom;
  const sid = chat.sessionId;

  $input.value = "";
  $input.style.height = "auto";
  $send.disabled = true;

  addUserBubble(chatDom, text);
  updateChatTitle(activeChatId, text);   // 첫 메시지면 사이드바 타이틀 갱신
  const aiRow = addAIContainer(chatDom);
  const ctx = { activeTools: {} };

  let finalText = "";
  let finalHtml = "";
  let finalSuggestions = [];

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sid, input: text }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      finalText = `오류: ${err.error || response.statusText}`;
    } else {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split("\\n\\n");
        buffer = parts.pop();
        for (const part of parts) {
          if (part.startsWith("data: ")) {
            try {
              const ev = JSON.parse(part.slice(6));
              if (ev.phase === "ai_response") {
                finalText = ev.text || "";
                finalHtml = ev.html || "";
                finalSuggestions = ev.suggestions || [];
              } else if (ev.phase === "error") {
                finalText = ev.text;
              } else {
                appendStepCard(aiRow, ev, ctx);
              }
            } catch (e) {
              console.warn("파싱 실패:", part, e);
            }
          }
        }
      }
    }
  } catch (e) {
    finalText = `네트워크 오류: ${e.message}`;
  }

  finalizeAI(aiRow, finalText, finalHtml, finalSuggestions);
  $send.disabled = false;
  $input.focus();
}

// ── 이벤트 바인딩 ──
$send.addEventListener("click", send);

$input.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

$input.addEventListener("input", () => {
  $input.style.height = "auto";
  $input.style.height = Math.min($input.scrollHeight, 160) + "px";
});

$newChatBtn.addEventListener("click", () => {
  const id = createChat();
  switchChat(id);
});

// ── 업무 프로세스 선택 모달 ──────────────────────────────────────────────
const $workflowChatBtn = document.getElementById("workflow-chat-btn");
const $wfModal = document.getElementById("wf-modal");
const $wfSearchInput = document.getElementById("wf-search-input");
const $wfList = document.getElementById("wf-list");
const $wfStartBtn = document.getElementById("wf-start-btn");
const $wfCancelBtn = document.getElementById("wf-cancel-btn");
const $wfCloseBtn = document.getElementById("wf-close-btn");

let workflowsCache = [];          // /workflows에서 받은 전체 목록
let selectedWorkflowId = null;    // 모달 안에서 선택된 항목

async function loadWorkflows() {
  try {
    const res = await fetch("/workflows");
    workflowsCache = await res.json();
  } catch (e) {
    console.warn("워크플로우 목록 로드 실패:", e);
    workflowsCache = [];
  }
}

function renderWorkflowList(query) {
  query = (query || "").trim().toLowerCase();
  $wfList.innerHTML = "";
  const filtered = workflowsCache.filter(wf => {
    if (!query) return true;
    if (wf.name.toLowerCase().includes(query)) return true;
    if (wf.description.toLowerCase().includes(query)) return true;
    if ((wf.keywords || []).some(k => k.toLowerCase().includes(query))) return true;
    return false;
  });

  if (filtered.length === 0) {
    $wfList.innerHTML = `<div class="wf-empty">검색 결과가 없습니다.</div>`;
    return;
  }

  for (const wf of filtered) {
    const opt = document.createElement("div");
    opt.className = "wf-option" + (wf.id === selectedWorkflowId ? " selected" : "");
    opt.dataset.workflowId = wf.id;
    opt.innerHTML = `
      <div class="wf-name">${escapeHtml(wf.name)}</div>
      <div class="wf-desc">${escapeHtml(wf.description || "(설명 없음)")}</div>
    `;
    opt.addEventListener("click", () => {
      selectedWorkflowId = wf.id;
      // 선택 highlight 갱신
      $wfList.querySelectorAll(".wf-option").forEach(el => el.classList.remove("selected"));
      opt.classList.add("selected");
      $wfStartBtn.disabled = false;
    });
    // 더블클릭 시 즉시 시작
    opt.addEventListener("dblclick", () => {
      selectedWorkflowId = wf.id;
      startWorkflowChat();
    });
    $wfList.appendChild(opt);
  }
}

function openWorkflowModal() {
  selectedWorkflowId = null;
  $wfStartBtn.disabled = true;
  $wfSearchInput.value = "";
  renderWorkflowList("");
  $wfModal.classList.add("active");
  setTimeout(() => $wfSearchInput.focus(), 50);
}

function closeWorkflowModal() {
  $wfModal.classList.remove("active");
  selectedWorkflowId = null;
}

function startWorkflowChat() {
  const wf = workflowsCache.find(w => w.id === selectedWorkflowId);
  if (!wf) return;

  // 1. 새 채팅 생성 + 활성화
  const id = createChat();
  const chat = chats.get(id);
  // 사이드바 타이틀을 워크플로우 한글명으로 미리 지정 (자동 갱신을 비활성화)
  chat.title = wf.name;
  switchChat(id);
  renderHistory();

  // 2. 모달 닫기
  closeWorkflowModal();

  // 3. 자동 시작 메시지 전송 → 워크플로우 키워드 매칭으로 컨텍스트 자동 주입
  $input.value = wf.start_phrase || `${wf.name} 시작해주세요`;
  send();
}

$workflowChatBtn.addEventListener("click", openWorkflowModal);
$wfCloseBtn.addEventListener("click", closeWorkflowModal);
$wfCancelBtn.addEventListener("click", closeWorkflowModal);
$wfStartBtn.addEventListener("click", startWorkflowChat);

// 오버레이 바깥 클릭 시 닫기
$wfModal.addEventListener("click", (e) => {
  if (e.target === $wfModal) closeWorkflowModal();
});

// ESC로 닫기 (열린 모달 모두)
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if ($wfModal.classList.contains("active")) closeWorkflowModal();
  if ($toolsModal && $toolsModal.classList.contains("active")) {
    $toolsModal.classList.remove("active");
  }
});

// 검색 입력 → 실시간 filter
$wfSearchInput.addEventListener("input", (e) => {
  renderWorkflowList(e.target.value);
});

// Enter로 시작 (선택된 항목 있을 때)
$wfSearchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && selectedWorkflowId) {
    startWorkflowChat();
  }
});

// 페이지 로드 시 워크플로우 목록 미리 fetch (모달 첫 클릭 지연 방지)
loadWorkflows();

// ── 도구·스킬 확인 모달 ──────────────────────────────────────────────────
const $toolsBtn = document.getElementById("tools-btn");
const $toolsModal = document.getElementById("tools-modal");
const $toolsSearch = document.getElementById("tools-search-input");
const $toolsList = document.getElementById("tools-list");
const $toolsClose = document.getElementById("tools-close-btn");

let toolsCache = [];

const TYPE_LABELS = {
  python:   "정확한 동작",
  llm:      "AI 판단",
  workflow: "워크플로우",
};

async function loadTools() {
  try {
    const res = await fetch("/tools");
    toolsCache = await res.json();
  } catch (e) {
    console.warn("도구 목록 로드 실패:", e);
    toolsCache = [];
  }
}

function renderToolCard(item) {
  const card = document.createElement("div");
  card.className = "tool-option";
  const badgeText = TYPE_LABELS[item.type] || item.type;

  let paramsHtml = "";
  if (item.parameters && Object.keys(item.parameters).length) {
    const lines = Object.entries(item.parameters).map(([k, v]) => {
      const required = (item.required || []).includes(k);
      const mark = required ? '<span class="param-required">*</span> ' : "";
      const typeText = (v && v.type) ? v.type : "any";
      const descText = (v && v.description) ? v.description : "";
      return `${mark}${escapeHtml(k)} <span style="color:#94A3B8">(${escapeHtml(typeText)})</span>: ${escapeHtml(descText)}`;
    });
    paramsHtml = `<div class="tool-params">${lines.join("<br>")}</div>`;
  }

  card.innerHTML = `
    <div class="tool-name">
      ${escapeHtml(item.name)}
      <span class="tool-id">${escapeHtml(item.id)}</span>
      <span class="tool-type-badge ${item.type}">${escapeHtml(badgeText)}</span>
    </div>
    <div class="tool-desc">${escapeHtml(item.description || "")}</div>
    ${paramsHtml}
  `;
  return card;
}

function renderToolsList(query) {
  query = (query || "").trim().toLowerCase();
  $toolsList.innerHTML = "";

  // 워크플로우 섹션 (workflowsCache 재사용)
  const wfFiltered = workflowsCache.filter(wf =>
    !query
    || wf.name.toLowerCase().includes(query)
    || wf.id.toLowerCase().includes(query)
    || (wf.description || "").toLowerCase().includes(query)
    || (wf.keywords || []).some(k => k.toLowerCase().includes(query))
  );
  if (wfFiltered.length) {
    const title = document.createElement("div");
    title.className = "tools-section-title";
    title.textContent = `📋 워크플로우 (${wfFiltered.length})`;
    $toolsList.appendChild(title);
    for (const wf of wfFiltered) {
      $toolsList.appendChild(renderToolCard({
        type: "workflow",
        id: wf.id, name: wf.name, description: wf.description,
        parameters: null, required: [],
      }));
    }
  }

  // 도구 섹션
  const toolFiltered = toolsCache.filter(t =>
    !query
    || t.name.toLowerCase().includes(query)
    || t.id.toLowerCase().includes(query)
    || (t.description || "").toLowerCase().includes(query)
  );
  if (toolFiltered.length) {
    const title = document.createElement("div");
    title.className = "tools-section-title";
    title.textContent = `🔧 도구 (${toolFiltered.length})`;
    $toolsList.appendChild(title);
    for (const t of toolFiltered) {
      $toolsList.appendChild(renderToolCard(t));
    }
  }

  if (!wfFiltered.length && !toolFiltered.length) {
    $toolsList.innerHTML = `<div class="wf-empty">검색 결과가 없습니다.</div>`;
  }
}

$toolsBtn.addEventListener("click", () => {
  $toolsSearch.value = "";
  renderToolsList("");
  $toolsModal.classList.add("active");
  setTimeout(() => $toolsSearch.focus(), 50);
});
$toolsClose.addEventListener("click", () => $toolsModal.classList.remove("active"));
$toolsModal.addEventListener("click", e => {
  if (e.target === $toolsModal) $toolsModal.classList.remove("active");
});
$toolsSearch.addEventListener("input", e => renderToolsList(e.target.value));

// 페이지 로드 시 도구 목록 prefetch
loadTools();

$reset.addEventListener("click", async () => {
  if (!confirm("현재 채팅을 초기화하시겠습니까?")) return;
  const chat = chats.get(activeChatId);
  if (!chat) return;
  try {
    await fetch("/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: chat.sessionId }),
    });
  } catch (e) { console.warn("reset 실패:", e); }
  // DOM 비우고 환영 메시지 다시 표시
  chat.dom.innerHTML = WELCOME_HTML;
  bindChipsInScope(chat.dom);
  chat.title = "새 채팅";
  renderHistory();
  scrollChatToBottom();
});

// ── 초기화: 첫 채팅 자동 생성 ──
const _initialId = createChat();
switchChat(_initialId);
$input.focus();
</script>

</body>
</html>
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Skill Base AI 웹 UI 서버")
    parser.add_argument("--host", default="0.0.0.0",
                        help="바인딩 호스트 (기본: 0.0.0.0 = 모든 인터페이스)")
    parser.add_argument("--port", type=int, default=5000,
                        help="포트 번호 (기본: 5000)")
    args = parser.parse_args()

    print()
    print("=" * 50)
    print(f"  Skill Base AI 웹 UI")
    print(f"  로컬:    http://localhost:{args.port}")
    print(f"  외부:    http://<서버IP>:{args.port}")
    print(f"  종료:    Ctrl+C")
    print("=" * 50)
    print()

    app.run(host=args.host, port=args.port, debug=False, threaded=True)
