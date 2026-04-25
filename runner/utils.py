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
def _extract_balanced_json(text):
    """
    텍스트에서 첫 번째 균형 잡힌 JSON 객체/배열 블록을 추출.
    문자열 리터럴 내부의 중괄호·대괄호는 카운팅에서 제외한다.
    설명 텍스트 + JSON, 여러 코드블록, 주변 잡담이 섞인 출력에 대비한 폴백.
    """
    if not text:
        return None
    # 첫 '{' 또는 '['
    start = -1
    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            break
    if start == -1:
        return None

    open_ch = text[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_json(text: str) -> dict:
    """
    JSON 파싱. 다음 변형까지 강건하게 처리:
      1) 단일 ```json ...``` 코드블록 래핑
      2) 설명 텍스트 + JSON (앞/뒤에 잡담)
      3) 여러 줄에 걸친 객체
    실패 시 {"_raw": text, "_parse_error": True} 반환.
    """
    if not isinstance(text, str):
        return {"_raw": str(text), "_parse_error": True}
    raw_input = text
    cleaned = text.strip()

    # 1차: 단일 코드펜스만 깎고 직접 시도
    fenced = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
    fenced = re.sub(r"\n?```\s*$", "", fenced).strip()
    try:
        return json.loads(fenced)
    except json.JSONDecodeError:
        pass

    # 2차: 텍스트 어디서든 첫 균형 JSON 블록 추출 (코드펜스 안/밖 무관)
    candidate = _extract_balanced_json(fenced) or _extract_balanced_json(cleaned)
    if candidate:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    return {"_raw": raw_input, "_parse_error": True}

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
