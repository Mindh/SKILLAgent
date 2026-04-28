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
        return {
            "phase": "workflow_loaded",
            "text": f"'{wf}' 워크플로우로 진행",
            "workflow_id": wf,
        }

    if role == "assistant" and content.startswith("[도구 호출:"):
        name = content.replace("[도구 호출:", "").replace("]", "").strip()
        return {
            "phase": "tool_call",
            "text": f"'{name}' 도구 사용 중...",
            "tool_name": name,
        }

    if role == "user" and content.startswith("[도구 실행 결과:"):
        body = content.split("\n", 1)[1] if "\n" in content else ""
        result = body.split("\n\n위 결과를")[0].strip()
        name = content.split("\n", 1)[0].replace("[도구 실행 결과:", "").replace("]", "").strip()
        return {
            "phase": "tool_result",
            "text": f"'{name}' 도구 사용 완료",
            "tool_name": name,
            "result": result[:500],  # 결과 본문 미리보기 (최대 500자)
        }

    if role == "assistant" and not content.startswith("["):
        return {"phase": "ai_response", "text": _clean_ai_response(content)}

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

    last_seen = before_len
    while thread.is_alive():
        time.sleep(0.05)
        cur_len = len(sess["messages"])
        if cur_len > last_seen:
            for i in range(last_seen, cur_len):
                ev = _classify_message(sess["messages"][i])
                if ev:
                    yield fmt(ev)
            last_seen = cur_len

    thread.join()

    # 잔여 메시지 flush
    for i in range(last_seen, len(sess["messages"])):
        ev = _classify_message(sess["messages"][i])
        if ev:
            yield fmt(ev)

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


# ── 인라인 챗 UI ─────────────────────────────────────────────────────────────

INDEX_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Skill Base AI</title>
<style>
  :root {
    --bg:        #0F172A;
    --panel:     #1E293B;
    --border:    #334155;
    --text:      #F1F5F9;
    --muted:     #94A3B8;
    --user:      #F59E0B;
    --ai:        #7C3AED;
    --tool:      #2563EB;
    --workflow:  #059669;
    --result:    #0891B2;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: 'Segoe UI', 'Apple SD Gothic Neo', sans-serif;
    background: var(--bg); color: var(--text);
    display: flex; flex-direction: column;
  }

  header {
    padding: 14px 24px; border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between;
    background: rgba(15,23,42,.85); backdrop-filter: blur(8px);
    position: sticky; top: 0; z-index: 10;
  }
  header h1 {
    font-size: 1.1rem; font-weight: 700;
    background: linear-gradient(90deg, #A78BFA, #60A5FA);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  header button {
    background: var(--panel); border: 1px solid var(--border);
    color: var(--text); padding: 6px 14px; border-radius: 8px;
    font-size: .82rem; cursor: pointer; transition: background .15s;
  }
  header button:hover { background: #2A3A50; }

  #chat {
    flex: 1; overflow-y: auto; padding: 24px;
    max-width: 880px; width: 100%; margin: 0 auto;
  }

  .row { display: flex; margin-bottom: 16px; gap: 12px; }
  .row.user { justify-content: flex-end; }

  .avatar {
    width: 32px; height: 32px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 1rem; flex-shrink: 0;
  }
  .row.ai .avatar { background: rgba(124,58,237,.25); border: 1px solid var(--ai); }
  .row.user .avatar { background: rgba(245,158,11,.25); border: 1px solid var(--user); order: 2; }

  .ai-content {
    display: flex; flex-direction: column; max-width: 75%; gap: 8px;
  }

  .bubble {
    padding: 12px 16px; border-radius: 14px;
    line-height: 1.6; font-size: .95rem;
    white-space: pre-wrap; word-break: break-word;
  }
  .row.user .bubble {
    background: rgba(245,158,11,.18); border: 1px solid rgba(245,158,11,.4);
    color: #FEF3C7; border-bottom-right-radius: 4px;
    max-width: 75%;
  }
  .row.ai .bubble {
    background: rgba(124,58,237,.15); border: 1px solid rgba(124,58,237,.4);
    color: #EDE9FE; border-bottom-left-radius: 4px;
  }

  /* 라이브 진행 표시 (단순 spinner, 모든 단계에서 동일 텍스트) */
  .live-progress {
    display: flex; align-items: center; gap: 10px; padding: 10px 14px;
    background: rgba(100,116,139,.12); border: 1px solid var(--border);
    border-radius: 12px; color: var(--muted); font-size: .88rem;
  }
  .spinner {
    width: 14px; height: 14px; border: 2px solid var(--border);
    border-top-color: #A78BFA; border-radius: 50%;
    animation: spin .8s linear infinite; flex-shrink: 0;
  }
  .spinner-sm {
    width: 12px; height: 12px; border: 2px solid rgba(255,255,255,.15);
    border-top-color: currentColor; border-radius: 50%;
    animation: spin .8s linear infinite; flex-shrink: 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* 인라인 단계 카드 (워크플로우 / 도구) */
  .step-card {
    border-radius: 10px; padding: 10px 14px; font-size: .88rem;
    line-height: 1.4;
    animation: slideIn .25s ease-out;
  }
  @keyframes slideIn {
    from { opacity: 0; transform: translateX(-8px); }
    to { opacity: 1; transform: none; }
  }

  .step-card.workflow {
    background: rgba(5,150,105,.12); border: 1px solid rgba(5,150,105,.4); color: #6EE7B7;
    display: flex; align-items: center; gap: 8px;
  }

  .step-card.tool {
    background: rgba(37,99,235,.12); border: 1px solid rgba(37,99,235,.4); color: #93C5FD;
    display: flex; flex-direction: column; gap: 8px;
  }
  .step-card.tool.done {
    background: rgba(8,145,178,.10); border-color: rgba(8,145,178,.4); color: #67E8F9;
  }
  .step-card.tool .header-line {
    display: flex; align-items: center; gap: 8px;
  }
  .step-card.tool .result-body {
    background: rgba(15,23,42,.5); border-radius: 6px; padding: 8px 10px;
    font-family: 'Consolas', 'Fira Code', monospace; font-size: .78rem;
    color: #CBD5E1; white-space: pre-wrap; word-break: break-all;
    max-height: 200px; overflow-y: auto;
  }

  .typing-cursor {
    display: inline-block; width: 2px; height: 1em;
    background: #A78BFA; margin-left: 2px;
    animation: blink 1s step-end infinite; vertical-align: text-bottom;
  }
  @keyframes blink { 50% { opacity: 0; } }

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
    flex: 1; resize: none; padding: 12px 16px; min-height: 48px; max-height: 160px;
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 12px; color: var(--text); font-size: .95rem;
    font-family: inherit; line-height: 1.5;
  }
  textarea:focus { outline: none; border-color: var(--ai); }
  #send {
    padding: 12px 22px; background: linear-gradient(135deg, #7C3AED, #2563EB);
    color: white; border: none; border-radius: 12px;
    font-size: .95rem; font-weight: 600; cursor: pointer;
    transition: transform .1s, opacity .15s;
  }
  #send:hover:not(:disabled) { transform: translateY(-1px); }
  #send:disabled { opacity: .5; cursor: not-allowed; }

  .hint {
    text-align: center; padding: 32px 16px; color: var(--muted);
    font-size: .9rem;
  }
  .hint .examples {
    display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;
    margin-top: 16px;
  }
  .example-chip {
    background: var(--panel); border: 1px solid var(--border);
    padding: 6px 14px; border-radius: 20px; font-size: .82rem;
    cursor: pointer; transition: background .15s;
  }
  .example-chip:hover { background: #2A3A50; color: var(--text); }
</style>
</head>
<body>

<header>
  <h1>🤖 Skill Base AI</h1>
  <button id="reset">세션 초기화</button>
</header>

<div id="chat">
  <div class="hint" id="welcome">
    안녕하세요! HR 업무를 도와드립니다.
    <div class="examples">
      <span class="example-chip" data-text="안녕하세요!">안녕하세요!</span>
      <span class="example-chip" data-text="1234 더하기 5678 계산해줘">1234 더하기 5678 계산해줘</span>
      <span class="example-chip" data-text="홍길동 직원 정보 알려줘">홍길동 직원 정보 알려줘</span>
      <span class="example-chip" data-text="휴직 신청하고 싶어요">휴직 신청하고 싶어요</span>
      <span class="example-chip" data-text="안녕을 영어로 번역해줘">안녕을 영어로 번역해줘</span>
    </div>
  </div>
</div>

<footer>
  <div class="input-wrap">
    <textarea id="input" placeholder="메시지를 입력하세요... (Shift+Enter: 줄바꿈, Enter: 전송)"></textarea>
    <button id="send">전송</button>
  </div>
</footer>

<script>
const SID = "web_" + Math.random().toString(36).slice(2, 10);
const $chat = document.getElementById("chat");
const $input = document.getElementById("input");
const $send = document.getElementById("send");
const $reset = document.getElementById("reset");
const $welcome = document.getElementById("welcome");

document.querySelectorAll(".example-chip").forEach(el => {
  el.addEventListener("click", () => {
    $input.value = el.dataset.text;
    $input.focus();
  });
});

function scrollToBottom() {
  $chat.scrollTop = $chat.scrollHeight;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => (
    {'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]
  ));
}

function addUserBubble(text) {
  if ($welcome) { $welcome.remove(); }
  const row = document.createElement("div");
  row.className = "row user";
  row.innerHTML = `
    <div class="bubble">${escapeHtml(text)}</div>
    <div class="avatar">👤</div>
  `;
  $chat.appendChild(row);
  scrollToBottom();
}

function addAIContainer() {
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
  $chat.appendChild(row);
  scrollToBottom();
  return row;
}

// tool_call → tool_result 카드 통합용 맵
function appendStepCard(aiRow, ev, ctx) {
  const content = aiRow.querySelector('.ai-content');
  const live = content.querySelector('[data-role="live"]');

  if (ev.phase === "workflow_loaded") {
    const card = document.createElement("div");
    card.className = "step-card workflow";
    card.innerHTML = `<span>📋</span> <span>${escapeHtml(ev.text)}</span>`;
    content.insertBefore(card, live);
    scrollToBottom();
  }
  else if (ev.phase === "tool_call") {
    const card = document.createElement("div");
    card.className = "step-card tool";
    card.innerHTML = `
      <div class="header-line">
        <div class="spinner-sm"></div>
        <span>🔧 '${escapeHtml(ev.tool_name)}' 도구 사용 중...</span>
      </div>
    `;
    ctx.activeTools[ev.tool_name] = card;
    content.insertBefore(card, live);
    scrollToBottom();
  }
  else if (ev.phase === "tool_result") {
    const card = ctx.activeTools[ev.tool_name];
    if (card) {
      card.classList.add("done");
      card.querySelector(".header-line").innerHTML = `
        <span>✅</span>
        <span>'${escapeHtml(ev.tool_name)}' 도구 사용 완료</span>
      `;
      const result = (ev.result || "").trim();
      if (result) {
        const body = document.createElement("div");
        body.className = "result-body";
        body.textContent = result;
        card.appendChild(body);
      }
      delete ctx.activeTools[ev.tool_name];
      scrollToBottom();
    }
  }
  // 그 외 phase는 카드 추가 X (spinner만 유지)
}

function finalizeAI(aiRow, finalText) {
  const content = aiRow.querySelector('.ai-content');
  const live = content.querySelector('[data-role="live"]');
  if (live) live.remove();

  if (!finalText || !finalText.trim()) {
    const empty = document.createElement("div");
    empty.className = "bubble";
    empty.style.color = "var(--muted)";
    empty.textContent = "(빈 응답)";
    content.appendChild(empty);
    return;
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = '<span data-role="text"></span><span class="typing-cursor"></span>';
  content.appendChild(bubble);

  typewriter(bubble.querySelector('[data-role="text"]'), finalText, () => {
    const cursor = bubble.querySelector(".typing-cursor");
    if (cursor) cursor.remove();
  });
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

  $input.value = "";
  $input.style.height = "auto";
  $send.disabled = true;

  addUserBubble(text);
  const aiRow = addAIContainer();
  const ctx = { activeTools: {} };

  let finalText = "";

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: SID, input: text }),
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
                finalText = ev.text;
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

  finalizeAI(aiRow, finalText);
  $send.disabled = false;
  $input.focus();
}

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

$reset.addEventListener("click", async () => {
  if (!confirm("세션을 초기화하시겠습니까?")) return;
  await fetch("/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: SID }),
  });
  location.reload();
});

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
