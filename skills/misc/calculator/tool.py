def execute(params: dict):
    try:
        num1 = float(params.get("num1"))
        num2 = float(params.get("num2"))
        operator = params.get("operator")

        if getattr(num1, "real", None) is None or getattr(num2, "real", None) is None or operator is None:
            raise ValueError("누락된 파라미터가 있습니다. (num1, num2, operator 필요)")

        if operator == "+":
            return num1 + num2
        elif operator == "-":
            return num1 - num2
        elif operator == "*":
            return num1 * num2
        elif operator == "/":
            if num2 == 0:
                raise ValueError("0으로 나눌 수 없습니다.")
            return num1 / num2
        else:
            raise ValueError(f"지원하지 않는 연산자입니다: {operator}")
    except Exception as e:
        return str(e)
