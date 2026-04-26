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


def run(user_input: str, messages: list = None, injected_workflows: set = None) -> dict:
    """
    단일 턴 실행 API.

    messages와 injected_workflows를 넘기면 이어서 대화(상태 유지).
    반환: {"success": bool, "message": str, "messages": list, "injected_workflows": set}
    """
    if not user_input or not user_input.strip():
        return {
            "success": False,
            "message": "입력이 비어 있습니다.",
            "messages": messages or [],
            "injected_workflows": injected_workflows or set(),
        }

    if messages is None:
        messages = []
    if injected_workflows is None:
        injected_workflows = set()

    message = loop.turn(user_input, messages, injected_workflows)
    return {
        "success": True,
        "message": message,
        "messages": messages,
        "injected_workflows": injected_workflows,
    }


def interactive_loop():
    print("====== Skill Base AI (Claude 하네스 스타일) ======")
    print("종료: 'exit' 또는 'quit'")
    print("=================================================")

    messages: list = []
    injected_workflows: set = set()

    while True:
        try:
            print("\n" + "=" * 50)
            user_input = input("[USER] ").strip()

            if user_input.lower() in ["exit", "quit"]:
                print("시스템을 종료합니다.")
                break
            if not user_input:
                continue

            result = run(user_input, messages=messages, injected_workflows=injected_workflows)
            messages = result["messages"]
            injected_workflows = result["injected_workflows"]

            print("\n" + "-" * 50)
            print("[AI]")
            print(result["message"])
            log(f"[Debug] 턴={sum(1 for m in messages if m['role'] == 'user' and '[워크플로우' not in m['content'])} | 주입된 워크플로우={injected_workflows}")

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
