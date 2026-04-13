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


def call_ai(system_prompt: str, user_prompt: str, temperature: float = 0) -> str:
    """
    실제 AI API 호출 함수 (Google Gemini / OpenAI 호환 API 사용 예시).
    """
    import openai
    
    key = os.environ.get("GEMINI_API_KEY", GEMINI_API_KEY)
    if not key or key == "여기에_API_KEY를_입력하세요":
        raise ValueError("API 키가 설정되지 않았습니다. runner/llm.py 파일 상단의 GEMINI_API_KEY를 설정해주세요.")

    # Google AI Studio의 OpenAI 호환 엔드포인트를 사용합니다. 
    # (원하시는 엔드포인트가 따로 있다면 base_url을 수정하세요)
    client = openai.OpenAI(
        api_key=key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )
        
    start_time = time.time()
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=temperature,
            messages=[
                {"role": "user", "content": f"[System Instructions]\n{system_prompt}\n\n[User Request]\n{user_prompt}"},
            ]
        )
        elapsed_time = time.time() - start_time
        log(f"[LLM] API 응답 소요 시간: {elapsed_time:.2f}초")
        return response.choices[0].message.content.strip()
    except Exception as e:
        elapsed_time = time.time() - start_time
        log(f"[LLM] API 호출 실패 (소요 시간: {elapsed_time:.2f}초) - {e}")
        return "{}"
