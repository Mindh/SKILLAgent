# -*- coding: utf-8 -*-
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from runner import loop
from runner.utils import log


def run(user_input: str, messages: list = None, injected_workflows: set = None,
        state: dict = None) -> dict:
    """
    단일 턴 실행 API.

    Phase 3부터는 state dict를 넘기는 것을 권장한다:
        state = {"messages": [...], "injected_workflows": set, "active_subagent": None|dict, ...}
        result = run(user_input, state=state)
        # state는 in-place로 갱신됨

    레거시 호출(messages, injected_workflows)도 지원하지만 active_subagent는 보존되지 않는다.

    반환: {"success", "message", "messages", "injected_workflows", "active_subagent",
           "tool_events", "artifacts", "subagent_history"}
    """
    if not user_input or not user_input.strip():
        return {
            "success": False,
            "message": "입력이 비어 있습니다.",
            "messages": (state or {}).get("messages", messages or []),
            "injected_workflows": (state or {}).get("injected_workflows", injected_workflows or set()),
            "active_subagent": (state or {}).get("active_subagent"),
            "tool_events": [],
            "artifacts": [],
            "subagent_history": (state or {}).get("subagent_history", []),
        }

    if state is None:
        state = {
            "messages": messages if messages is not None else [],
            "injected_workflows": injected_workflows if injected_workflows is not None else set(),
            "active_subagent": None,
            "subagent_history": [],
            "last_tool_events": [],
            "last_artifacts": [],
        }

    message = loop.turn(user_input, state)
    return {
        "success": True,
        "message": message,
        "messages": state["messages"],
        "injected_workflows": state["injected_workflows"],
        "active_subagent": state.get("active_subagent"),
        "tool_events": state.get("last_tool_events", []),
        "artifacts": state.get("last_artifacts", []),
        "subagent_history": state.get("subagent_history", []),
    }


def interactive_loop():
    print("====== Skill Base AI (Claude 하네스 스타일) ======")
    print("종료: 'exit' 또는 'quit'")
    print("=================================================")

    state: dict = {
        "messages": [],
        "injected_workflows": set(),
        "active_subagent": None,
        "subagent_history": [],
        "last_tool_events": [],
        "last_artifacts": [],
    }

    while True:
        try:
            print("\n" + "=" * 50)
            user_input = input("[USER] ").strip()

            if user_input.lower() in ["exit", "quit"]:
                print("시스템을 종료합니다.")
                break
            if not user_input:
                continue

            result = run(user_input, state=state)

            print("\n" + "-" * 50)
            print("[AI]")
            print(result["message"])
            sub = state.get("active_subagent")
            sub_label = sub["workflow_id"] if sub else "(없음)"
            log(f"[Debug] 턴={sum(1 for m in state['messages'] if m['role'] == 'user' and '[워크플로우' not in m['content'])} | 활성 워크플로우={sub_label} | 종료된 워크플로우 수={len(state.get('subagent_history', []))}")

        except KeyboardInterrupt:
            print("\n시스템을 종료합니다.")
            break
        except Exception as e:
            print(f"\n[오류] {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
        result = run(user_input)
        print("\n" + "=" * 50)
        print("[AI]")
        print(result["message"])
    else:
        interactive_loop()
