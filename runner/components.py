import os
import json
import importlib.util

from runner.utils import load_file, log, parse_json, BASE_DIR
from runner.llm import call_ai

def load_tool_module(skill_id: str):
    path = os.path.join(BASE_DIR, "skills", "tools", f"{skill_id}_tool.py")
    spec = importlib.util.spec_from_file_location(f"tool_{skill_id}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def run_skill(skill_id: str, user_input: str, config: dict):
    skill_prompt = load_file(f"skills/worker_prompts/{skill_id}_skill.md")
    base_system = load_file("prompts/base_system.md")

    system = f"{base_system}\n\n---\n{skill_prompt}"
    
    tool_path = f"skills/tools/{skill_id}_tool.py"
    if os.path.exists(os.path.join(BASE_DIR, tool_path)):
        log(f"함수형 스킬 감지됨: {tool_path}")
        tool_module = load_tool_module(skill_id)
        
        feedback = ""
        max_attempts = config.get("max_iterations", 3)
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                log(f"[Tool Error Recovery] 스킬 {skill_id} 루프 {attempt}/{max_attempts} 재시도 중...")
                retry_prompt = f"{user_input}\n\n[이전 파라미터 생성/실행 중 에러 발생]\n{feedback}\n에러를 확인하고 파라미터를 수정하여 다시 완전한 JSON만 생성하세요."
                raw_params = call_ai(system_prompt=system, user_prompt=retry_prompt, temperature=config["temperature"])
            else:
                raw_params = call_ai(system_prompt=system, user_prompt=user_input, temperature=config["temperature"])
            
            log(f"추출된 파라미터: {raw_params[:200]}...")
            params = parse_json(raw_params)
            
            # --- Slot Filling / 필수 정보 대기 판별 ---
            if isinstance(params, dict) and params.get("_status") == "require_info":
                return True, json.dumps(params, ensure_ascii=False)
            
            if isinstance(params, dict) and "_parse_error" in params:
                feedback = f"JSON 파싱 실패 (생성된 텍스트가 유효한 JSON이 아님). 원본: {raw_params}"
                continue
                
            try:
                result = tool_module.execute(params)
                return True, json.dumps({"function_result": result, "extracted_params": params}, ensure_ascii=False)
            except Exception as e:
                feedback = f"툴 함수 실행 중 익셉션 에러 발생: {type(e).__name__}({str(e)})"
                log(feedback)
                
        # 최대 반복 횟수를 초과해도 실패한 경우
        return True, json.dumps({"_status": "tool_failure", "error": feedback}, ensure_ascii=False)

    raw = call_ai(system_prompt=system, user_prompt=user_input, temperature=config["temperature"])
    log(f"스킬 {skill_id} 원본 출력: {raw[:200]}")
    return False, raw

def run_judge(user_input: str, skill_output: str, skill_id: str, config: dict) -> dict:
    judge_prompt = load_file("skills/system_prompts/judge_skill.md")
    base_system = load_file("prompts/base_system.md")

    system = f"{base_system}\n\n---\n{judge_prompt}"
    user = (
        f"original_request: {user_input}\n"
        f"skill_output: {skill_output}\n"
        f"skill_id: {skill_id}"
    )

    raw = call_ai(system_prompt=system, user_prompt=user, temperature=config["temperature"])
    result = parse_json(raw)

    if "_parse_error" in result:
        log("Judge 파싱 실패 → 기본값 반환")
        return {"score": 0, "max": 10, "pass": False, "feedback": "Judge 출력 파싱 실패"}

    log(f"Judge 점수: {result.get('score')}/10 | pass: {result.get('pass')} | feedback: {result.get('feedback')}")
    return result

def run_refine(user_input: str, previous_output: str, feedback: str, skill_id: str, attempt: int, config: dict) -> str:
    refine_prompt = load_file("skills/system_prompts/refine_skill.md")
    base_system = load_file("prompts/base_system.md")

    system = f"{base_system}\n\n---\n{refine_prompt}"
    user = (
        f"original_request: {user_input}\n"
        f"previous_output: {previous_output}\n"
        f"feedback: {feedback}\n"
        f"skill_id: {skill_id}\n"
        f"attempt: {attempt}"
    )

    raw = call_ai(system_prompt=system, user_prompt=user, temperature=config["temperature"])
    log(f"Refine 출력 (attempt {attempt}): {raw[:200]}")
    return raw
