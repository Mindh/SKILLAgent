# -*- coding: utf-8 -*-
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from runner.utils import load_config, log
from runner.skill_retriever import ensure_index_ready
from runner.agent_retriever import ensure_agent_index_ready
from runner import supervisor


def _init_runtime():
    """스킬/에이전트 임베딩 인덱스 초기화. 임베딩 실패해도 keyword 폴백으로 계속."""
    try:
        ensure_index_ready()
    except Exception as e:
        log(f"[Warning] 스킬 인덱스 초기화 중 오류 (폴백 사용): {e}")
    try:
        ensure_agent_index_ready()
    except Exception as e:
        log(f"[Warning] 에이전트 인덱스 초기화 중 오류 (폴백 사용): {e}")


def run(user_input: str, session: dict = None) -> dict:
    """
    supervisor 기반 단일 턴 실행.
    session을 넘기면 이어서 대화(상태 유지), 없으면 매 호출마다 새 세션.

    반환: {"success": bool, "message": str, "session": dict}
    """
    _init_runtime()
    config = load_config()

    if not user_input or not user_input.strip():
        return {"success": False, "message": "입력이 비어 있습니다.", "session": session or {}}

    if session is None:
        session = {}

    result = supervisor.turn(user_input, session, config)
    return {"success": True, "message": result["message"], "session": result["session"]}


def interactive_loop():
    print("====== Skill Base AI Interactive (Supervisor) ======")
    print("종료: 'exit' 또는 'quit'")
    print("====================================================")

    session = {}

    while True:
        try:
            print("\n" + "=" * 50)
            user_input = input("[USER] ").strip()

            if user_input.lower() in ["exit", "quit"]:
                print("시스템을 종료합니다.")
                break
            if not user_input:
                continue

            result = run(user_input, session=session)
            session = result["session"]

            print("\n" + "-" * 50)
            print("[AI]")
            print(result["message"])
            _print_session_debug(session)

        except KeyboardInterrupt:
            print("\n시스템을 종료합니다.")
            break
        except Exception as e:
            print(f"\n[오류] {e}")


def _print_session_debug(session: dict):
    """현재 세션 상태를 간략히 표시."""
    active = session.get("active_agent")
    paused = session.get("paused_agents", [])
    pending = session.get("pending_switch")
    bits = []
    if active:
        bits.append(f"active={active['agent_id']}({active.get('status','?')})")
    else:
        bits.append("active=None")
    if paused:
        bits.append(f"paused=[{', '.join(p['agent_id'] for p in paused)}]")
    if pending:
        bits.append(f"pending_switch→{pending.get('target')}")
    print("  ⎿ " + " | ".join(bits))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
        result = run(user_input)
        print("\n" + "=" * 50)
        print("[AI]")
        print(result["message"])
    else:
        interactive_loop()
