import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')

import json
from runner.utils import load_file, load_config, log, parse_json, build_context, build_chat_history
from runner.llm import call_ai
from runner.components import run_skill, run_judge, run_refine
from runner.router import route
from runner.skill_retriever import ensure_index_ready

# ── 메인 실행 루프 ─────────────────────────────────────────
def _make_final_response(skill_id: str, parsed_output) -> str:
    """
    LLM 스킬의 검증된 출력을 사람이 읽기 좋은 최종 응답 문자열로 변환합니다.
    router를 경유하지 않고 즉시 사용자에게 반환할 텍스트를 만듭니다.
    """
    if isinstance(parsed_output, str):
        return parsed_output

    if not isinstance(parsed_output, dict):
        return str(parsed_output)

    # 스킬별 핵심 필드를 우선적으로 꺼내 자연스러운 문장으로 변환
    skill_key_map = {
        "translate":  ("translated",  lambda d: f"번역 결과: {d['translated']}\n(원문 언어: {d.get('source_lang','?')} → {d.get('target_lang','?')})"),
        "summarize":  ("summary",     lambda d: f"요약 결과:\n{d['summary']}"),
        "extract":    ("keywords",    lambda d: f"추출된 키워드:\n" + "\n".join(f"- {k}" for k in (d['keywords'] if isinstance(d['keywords'], list) else [d['keywords']]))),
    }

    if skill_id in skill_key_map:
        key, formatter = skill_key_map[skill_id]
        if key in parsed_output:
            try:
                return formatter(parsed_output)
            except Exception:
                pass  # 포맷 실패 시 아래 fallback으로

    # response 키가 있으면 그대로 사용
    if "response" in parsed_output:
        return parsed_output["response"]

    # 최후 수단: JSON 덤프
    return json.dumps(parsed_output, ensure_ascii=False, indent=2)


def run(user_input: str, history: list = None, global_state: dict = None) -> dict:
    if global_state is None:
        global_state = {}
    
    # 스킬 임베딩 인덱스 초기화 (캐싱된 경우 API 재호출 없음)
    ensure_index_ready()
        
    config = load_config()
    log(f"설정 로드 완료: {config}")
    log(f"입력: {user_input}")

    # 1. 입력 검증
    if not user_input or not user_input.strip():
        return {"success": False, "error": "입력이 비어 있습니다.", "output": None}

    pipeline_results = []
    pipeline_plan = []
    total_iterations = 0
    MAX_STEPS = config.get("max_pipeline_steps", 5)
    step_count = 0

    while step_count < MAX_STEPS:
        # 2. 루프 내 상태 갱신
        if history and len(history) > 0:
            chat_context = build_chat_history(history)
            assembled_input = f"[최근 대화 기록]\n{chat_context}\n\n[사용자 최신 요청]\n{user_input}"
        else:
            assembled_input = user_input
            
        if global_state:
            state_str = json.dumps(global_state, ensure_ascii=False, indent=2)
            assembled_input = f"[현재 작업 상태 공간]\n```json\n{state_str}\n```\n\n{assembled_input}"
            
        current_input = assembled_input

        # 3. 다음 행동 파악 (ReAct / Observation 로직)
        pipeline = route(user_input, config, history=history, global_state=global_state)
        step = pipeline[0]
        skill_id = step["skill_id"]
        reason = step.get("reason", "이유 없음")
        
        pipeline_plan.append(step)
        log(f"\n▶ [Dynamic Step {step_count + 1}/{MAX_STEPS}] Next Action: {skill_id} | Reason: {reason}")

        # 4. 일반 대화(chat) 이거나 파이프라인 종료 조건일 경우
        if skill_id == "chat":
            log("작업 완료 - 일반 대화(chat) 응답 생성")
            if "direct_response" in step:
                log("Fast-Track 적용: 추가 호출 없이 라우터 응답을 직접 사용합니다.")
                chat_output = step["direct_response"]
            else:
                base_system = load_file("prompts/base_system.md")
                chat_output = call_ai(system_prompt=base_system, user_prompt=current_input, temperature=config["temperature"])
            
            step_result = {
                "skill_id": "chat",
                "output": {"response": chat_output},
                "raw_output": chat_output,
                "final_score": 10,
                "iterations": 1,
                "feedback_history": []
            }
            pipeline_results.append(step_result)
            total_iterations += 1
            global_state[skill_id] = chat_output
            break # 챗 응답이 생성되면 더 이상 액션 불필요, 종료.

        # 5. 함수형 스킬 실행
        is_tool, current_output = run_skill(skill_id, current_input, config)
        
        # --- Slot Filling / 필수 정보 대기 공통 로직 ---
        check_parsed = parse_json(current_output)
        if isinstance(check_parsed, dict) and check_parsed.get("_status") == "require_info":
            log("스킬 필수 정보 누락 감지됨. 일시중지 및 사용자 질의 모드 전환.")
            ask_msg = check_parsed.get("ask_user", "추가 정보가 필요합니다.")
            step_result = {
                "skill_id": skill_id,
                "output": {"response": ask_msg, "status": "require_info"},
                "raw_output": current_output,
                "final_score": 10,
                "iterations": 1,
                "feedback_history": []
            }
            pipeline_results.append(step_result)
            total_iterations += 1
            break # 사용자 답변 대기 위해 종료
        
        # --- 툴 에러 완전 실패 공통 로직 ---
        if isinstance(check_parsed, dict) and check_parsed.get("_status") == "tool_failure":
            log(f"툴 실행 최종 실패 감지됨: {check_parsed.get('error')}")
            step_result = {
                "skill_id": skill_id,
                "output": {"response": f"죄송합니다. 작업 중 오류가 발생했습니다: {check_parsed.get('error')}", "status": "tool_failure"},
                "raw_output": current_output,
                "final_score": 0,
                "iterations": config.get("max_iterations", 3),
                "feedback_history": []
            }
            pipeline_results.append(step_result)
            total_iterations += config.get("max_iterations", 3)
            break
        
        if is_tool:
            log("함수형 스킬 실행 완료 - 상태 갱신 후 루프 컨티뉴")
            final_parsed = check_parsed
            step_result = {
                "skill_id": skill_id,
                "output": final_parsed,
                "raw_output": current_output,
                "final_score": 10,
                "iterations": 1,
                "feedback_history": []
            }
            pipeline_results.append(step_result)
            total_iterations += 1
            global_state[skill_id] = final_parsed
            step_count += 1
            continue

        # 6. Agentic Loop (LLM 텍스트 추론 기반 스킬일 경우)
        feedback_history = []
        skill_passed = False
        for attempt in range(1, config["max_iterations"] + 1):
            log(f"\n── 스킬 {skill_id} 평가 루프 {attempt}/{config['max_iterations']} ──")
            judge_result = run_judge(current_input, current_output, skill_id, config)
            score = judge_result.get("score", 0)
            passed = judge_result.get("pass", False)
            feedback = judge_result.get("feedback", "")
            feedback_history.append({"attempt": attempt, "score": score, "feedback": feedback})

            if passed or score >= config["pass_threshold"]:
                skill_passed = True
                break
            if attempt == config["max_iterations"]:
                break

            context_summary = build_context(feedback_history, config["context_window"])
            refine_input = f"{current_input}\n\n[이전 시도 요약]\n{context_summary}" if len(feedback_history) > 1 else current_input
            current_output = run_refine(refine_input, current_output, feedback, skill_id, attempt, config)

        final_parsed = parse_json(current_output)
        final_score = feedback_history[-1]["score"] if feedback_history else 0
        total_iterations += len(feedback_history)

        final_valid_output = final_parsed if isinstance(final_parsed, dict) and '_parse_error' not in final_parsed else current_output
        global_state[skill_id] = final_valid_output
        step_count += 1

        # ── 조기 종료 판단 ──────────────────────────────────────
        # LLM 스킬이 judge를 통과했으면 이 스킬이 최종 응답입니다.
        # router를 다시 호출하지 않고 스킬 출력에서 직접 최종 응답을 생성합니다.
        # (툴 스킬(is_tool=True)은 위 블록에서 이미 continue/break 처리됨)
        if skill_passed:
            log(f"✔ 스킬 [{skill_id}] judge 통과 → 즉시 종료 (불필요한 router 재호출 없음)")
            final_response_text = _make_final_response(skill_id, final_valid_output)
            step_result = {
                "skill_id": skill_id,
                "output": {"response": final_response_text, "_source": final_valid_output},
                "raw_output": current_output,
                "final_score": final_score,
                "iterations": len(feedback_history),
                "feedback_history": feedback_history,
            }
            pipeline_results.append(step_result)
            break  # ← 핵심: router 재진입 없이 즉시 종료

        # judge 불통과(max_iterations 소진)인 경우에만 루프 재진입으로 router의 판단에 맡김
        log(f"✖ 스킬 [{skill_id}] judge 미통과 (score={final_score}) → router에 다음 행동 위임")
        step_result = {
            "skill_id": skill_id,
            "output": final_valid_output,
            "raw_output": current_output,
            "final_score": final_score,
            "iterations": len(feedback_history),
            "feedback_history": feedback_history,
        }
        pipeline_results.append(step_result)

    if step_count >= MAX_STEPS:
        log("최대 파이프라인 스텝 제한에 도달하여 강제 종료합니다.")

    # 7. 최종 결과 반환
    final_output = pipeline_results[-1]["output"] if pipeline_results else None
    final_raw = pipeline_results[-1]["raw_output"] if pipeline_results else None

    return {
        "success": True,
        "pipeline_plan": pipeline_plan,
        "pipeline_results": pipeline_results,
        "output": final_output,
        "raw_output": final_raw,
        "iterations": total_iterations
    }

# ── 결과 출력 유틸 ─────────────────────────────────────────
def print_simple_result(result: dict):
    print(f"상태: {'✅ 성공' if result.get('success') else '❌ 실패'}")
    
    if "pipeline_plan" in result:
        plan = [item.get("skill_id", "unknown") for item in result.get("pipeline_plan", [])]
        print(f"동작 스킬: {' ➜ '.join(plan)}")
    
    print("-" * 50)
    print("▶ 최종 데이터:")
    output_data = result.get("output")
    if not output_data:
        output_data = result.get("raw_output", "결과 없음")
        
    if isinstance(output_data, dict):
        print(json.dumps(output_data, ensure_ascii=False, indent=2))
    else:
        print(output_data)

# ── 진입점 ─────────────────────────────────────────────────
def interactive_loop():
    print("====== Skill Base AI Interactive Test ======")
    print("종료하려면 'exit' 또는 'quit'를 입력하세요.")
    print("============================================")
    
    session_history = []
    global_state = {}
    
    while True:
        try:
            print("\n" + "=" * 50)
            user_input = input("[USER] 질문을 입력하세요: ").strip()
            
            if user_input.lower() in ["exit", "quit"]:
                print("시스템을 종료합니다.")
                break
                
            if not user_input:
                continue
                
            result = run(user_input, history=session_history, global_state=global_state)
            
            print("\n" + "=" * 50)
            print("[AI 최종 결과 요약]")
            print("=" * 50)
            print_simple_result(result)
            
            # 히스토리에 저장하기 위한 AI 응답 추출
            final_output = result.get("output", {})
            if isinstance(final_output, dict) and "response" in final_output:
                ai_text = final_output["response"]
            else:
                ai_text = json.dumps(final_output, ensure_ascii=False)
                
            session_history.append({"user": user_input, "ai": ai_text})
            
        except KeyboardInterrupt:
            print("\n시스템을 종료합니다.")
            break
        except Exception as e:
            print(f"\n[오류 발생] {e}")

if __name__ == "__main__":
    import sys
    import os
    # 상위 폴더 경로를 sys.path에 추가하여 모듈 import 시 오류 방지
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # 인자가 있는 경우 단일 실행 모드로 동작
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
        result = run(user_input, global_state={})
        
        print("\n" + "=" * 50)
        print("[AI 최종 결과 요약]")
        print("=" * 50)
        print_simple_result(result)
    else:
        # 인자가 없는 경우 대화형 모드로 진입
        interactive_loop()
