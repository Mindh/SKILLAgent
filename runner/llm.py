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
MODEL_NAME = "gemma-4-31b-it"


def call_ai(system_prompt: str, user_prompt: str, temperature: float = 0) -> str:
    """
    LLM 호출 — system_prompt와 user_prompt를 받아 응답 텍스트를 반환.

    이 함수 하나만 자체 모델용으로 교체하면:
      - loop.py(ReAct 루프)
      - 모든 LLM 도구(translate, summarize, jd_generator 등)
    가 모두 새 백엔드를 사용한다.

    ── 자체 모델 연결 예시 (requests 사용) ──

        import requests
        def call_ai(system_prompt, user_prompt, temperature=0):
            r = requests.post(
                "http://my-server/v1/chat/completions",
                json={
                    "model": MODEL_NAME,
                    "messages": [
                        {"role": "user",
                         "content": f"[System Instructions]\\n{system_prompt}\\n\\n[User Request]\\n{user_prompt}"},
                    ],
                    "temperature": temperature,
                },
            )
            return r.json()["choices"][0]["message"]["content"] or ""
    """
    import openai

    key = os.environ.get("GEMINI_API_KEY", GEMINI_API_KEY)
    if not key or key == "여기에_API_KEY를_입력하세요":
        raise ValueError("API 키가 설정되지 않았습니다. runner/llm.py 파일 상단의 GEMINI_API_KEY를 설정해주세요.")

    client = openai.OpenAI(
        api_key=key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    start = time.time()
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=temperature,
            messages=[
                {"role": "user",
                 "content": f"[System Instructions]\n{system_prompt}\n\n[User Request]\n{user_prompt}"},
            ],
        )
        log(f"[LLM] API 응답 소요 시간: {time.time() - start:.2f}초")
        return response.choices[0].message.content or ""
    except Exception as e:
        log(f"[LLM] API 호출 실패 ({time.time() - start:.2f}초) - {e}")
        return ""
