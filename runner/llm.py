# -*- coding: utf-8 -*-
import os
import time
from runner.utils import log

# .env 파일 자동 로드 (python-dotenv 설치 시)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # 미설치 시 환경변수에서 직접 읽음

# API 키: 환경변수 GEMINI_API_KEY 또는 .env 파일에 설정하세요
# 예) export GEMINI_API_KEY="AIzaSy..."   (Linux/Mac)
#     setx GEMINI_API_KEY "AIzaSy..."     (Windows)
GEMINI_API_KEY = ""   # ← 직접 입력하거나 .env / 환경변수로 설정

# Google AI Studio 등에서 제공하는 모델명으로 필요 시 수정하세요
MODEL_NAME = "gemma-3-27b-it"


def call_ai_messages(messages: list, temperature: float = 0) -> str:
    """
    messages 리스트 기반 LLM 호출 (loop.py의 ReAct 루프가 사용).

    messages: [{"role": "user"|"assistant", "content": "..."}, ...]
    반환값: 모델 응답 텍스트 (실패 시 빈 문자열)

    ── 자체 모델 연결 시 ──
    이 함수의 본문만 교체하면 된다. 예를 들어 requests로 자체 서버를 호출:

        import requests
        def call_ai_messages(messages, temperature=0):
            r = requests.post(
                "http://my-server/v1/chat/completions",
                json={"model": MODEL_NAME, "messages": messages, "temperature": temperature},
            )
            return r.json()["choices"][0]["message"]["content"] or ""
    """
    import openai

    key = os.environ.get("GEMINI_API_KEY", GEMINI_API_KEY)
    if not key or key == "여기에_API_KEY를_입력하세요":
        raise ValueError("API 키가 설정되지 않았습니다. runner/llm.py 파일 상단의 GEMINI_API_KEY를 설정해주세요.")

    client = openai.OpenAI(
        api_key=key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )

    start_time = time.time()
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=temperature,
            messages=messages,
        )
        elapsed = time.time() - start_time
        log(f"[LLM] API 응답 소요 시간: {elapsed:.2f}초")
        return response.choices[0].message.content or ""
    except Exception as e:
        elapsed = time.time() - start_time
        log(f"[LLM] API 호출 실패 (소요 시간: {elapsed:.2f}초) - {e}")
        return ""


def call_ai(system_prompt: str, user_prompt: str, temperature: float = 0) -> str:
    """
    단일 system+user 프롬프트 호출 (skills/worker_prompts/*_skill.md 도구가 사용).

    내부적으로 call_ai_messages를 호출하므로, 자체 모델 연결 시 call_ai_messages만
    교체하면 LLM 도구들도 자동으로 새 백엔드를 사용한다.
    """
    text = call_ai_messages(
        messages=[
            {"role": "user", "content": f"[System Instructions]\n{system_prompt}\n\n[User Request]\n{user_prompt}"},
        ],
        temperature=temperature,
    )
    return text.strip() if text else "{}"
