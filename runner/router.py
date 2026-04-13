# -*- coding: utf-8 -*-
import json
from runner.utils import load_file, log, parse_json, build_chat_history
from runner.llm import call_ai
from runner.skill_retriever import retrieve_top_k_skills, get_all_valid_skill_ids

def route(user_input: str, config: dict, history: list = None, global_state: dict = None) -> list:
    # RAG 기반 스킬 검색: config에서 모드/Top-K 읽기
    retrieval_mode = config.get("skill_retrieval_mode", "full")
    retrieval_k = config.get("skill_retrieval_top_k", 3)

    # 검색 대상 쿼리는 user_input 기반 (global_state는 라우터 프롬프트에 별도 주입)
    registry_block = retrieve_top_k_skills(user_input, k=retrieval_k, mode=retrieval_mode)

    router_template = load_file("prompts/router_prompt.md")
    base_system = load_file("prompts/base_system.md")

    router_prompt = router_template.replace("{REGISTRY_CONTENT}", registry_block)
    
    if history and len(history) > 0:
        chat_context = build_chat_history(history)
        assembled_input = f"[최근 대화 기록]\n{chat_context}\n\n"
    else:
        assembled_input = ""
        
    if global_state:
        state_str = json.dumps(global_state, ensure_ascii=False, indent=2)
        assembled_input += f"[현재 작업 상태 공간]\n```json\n{state_str}\n```\n\n"
        
    assembled_input += f"[사용자 최신 요청]\n{user_input}"
        
    router_prompt = router_prompt.replace("{USER_INPUT}", assembled_input)

    raw_output = call_ai(
        system_prompt=base_system,
        user_prompt=router_prompt,
        temperature=config["temperature"]
    ).strip()

    # Fast-Track (일반 대화) 판별: JSON 구조([, {, ```json)로 시작하지 않으면 평문 대화로 간주
    if not (raw_output.startswith("[") or raw_output.startswith("{") or raw_output.startswith("```json")):
        log("라우터 Fast-Track(일반 대화 또는 작업 완료) 감지됨")
        return [{"skill_id": "chat", "direct_response": raw_output}]

    parsed = parse_json(raw_output)
    
    # 폴백 로직
    fallback = [{"skill_id": "chat", "reason": "라우터 응답 파싱 실패"}]
    
    if isinstance(parsed, dict) and "_parse_error" in parsed:
        log("라우터 JSON 파싱 실패 → chat으로 폴백")
        return fallback

    # 딕셔너리로 단건 반환된 경우 리스트로 감싸기
    if isinstance(parsed, dict):
        parsed = [parsed]

    if not isinstance(parsed, list) or len(parsed) == 0:
        log("라우터가 빈 리스트 반환 → chat으로 폴백")
        return fallback

    # 여러 개가 오더라도 첫 번째 액션만 취함 (Next Action)
    next_action = parsed[0]

    # skill_registry.json에서 동적으로 유효 ID 목록 로드 (하드코딩 제거)
    valid_ids = get_all_valid_skill_ids()
    
    if not isinstance(next_action, dict) or "skill_id" not in next_action:
        next_action = {"skill_id": "chat", "reason": "형식 오류로 복구됨"}
    else:
        skill_id = next_action["skill_id"].strip().lower()
        if skill_id not in valid_ids:
            log(f"라우터가 잘못된 ID '{skill_id}' 반환 → chat으로 폴백")
            next_action["skill_id"] = "chat"
        else:
            next_action["skill_id"] = skill_id

    log(f"라우터 선택 Next Action: {next_action}")
    return [next_action]
