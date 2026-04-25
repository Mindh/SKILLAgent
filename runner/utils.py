# -*- coding: utf-8 -*-
import json
import os
import re

# ── 설정 로드 ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_file(path: str) -> str:
    with open(os.path.join(BASE_DIR, path), "r", encoding="utf-8") as f:
        return f.read()

# 런타임 불변 텍스트(프롬프트, agent definition 등)를 메모이즈.
# 키는 path 그대로. 파일 핫리로드가 필요하면 load_file을 사용.
_FILE_CACHE: dict = {}

def cached_file(path: str) -> str:
    if path in _FILE_CACHE:
        return _FILE_CACHE[path]
    content = load_file(path)
    _FILE_CACHE[path] = content
    return content

def load_config() -> dict:
    raw = load_file("prompts/loop_config.md")
    config = {}
    for line in raw.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            config[k.strip()] = v.strip()
    return {
        "max_iterations": int(config.get("max_iterations", 3)),
        "pass_threshold": int(config.get("pass_threshold", 7)),
        "force_exit_on_max": config.get("force_exit_on_max", "true").lower() == "true",
        "context_window": int(config.get("context_window", "last_2").replace("last_", "")),
        "temperature": float(config.get("temperature", 0)),
        "skill_retrieval_top_k": int(config.get("skill_retrieval_top_k", 3)),
        "skill_retrieval_mode": config.get("skill_retrieval_mode", "full"),
        "agent_retrieval_top_k": int(config.get("agent_retrieval_top_k", 3)),
        "enable_resume_hint": config.get("enable_resume_hint", "true").lower() == "true",
    }

# ── 파싱 및 유틸 ────────────────────────────────────────────
def parse_json(text: str) -> dict:
    """JSON 파싱. 코드블록 감싸인 경우도 처리."""
    text = text.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text, "_parse_error": True}

def build_context(history: list, window: int) -> str:
    """피드백 이력에서 최근 N개만 문자열로 조합"""
    recent = history[-window:]
    return "\n".join([f"[시도 {h['attempt']}] 피드백: {h['feedback']}" for h in recent])

def build_chat_history(history: list, window: int = 4) -> str:
    """대화 기록(채팅)에서 최근 N개를 [USER] / [AI] 형태의 문자열로 조합"""
    if not history:
        return "기록 없음"
    recent = history[-window:]
    lines = []
    for turn in recent:
        lines.append(f"[USER] {turn['user']}")
        lines.append(f"[AI] {turn['ai']}")
    return "\n".join(lines)

def log(message: str):
    print(f"[RUN] {message}")
