# -*- coding: utf-8 -*-
"""
mailto: URL 생성기.

브라우저/메일 클라이언트의 메일 작성 화면을 미리 채워서 여는 URL을 만든다.
교육 입과 안내 포스터 발송 등에서 사용.
"""
from urllib.parse import quote


def execute(params: dict):
    """
    params:
      - subject: 메일 제목 (필수)
      - body:    메일 본문 (필수, 평문)
      - to:      받는 사람 이메일 (선택, 기본 빈 값)

    반환:
      성공 시: {"status": "success", "mail_url": "mailto:?subject=...&body=..."}
      실패 시: {"status": "error",   "message": "..."}
    """
    subject = (params.get("subject") or "").strip()
    body = (params.get("body") or "").strip()
    to = (params.get("to") or "").strip()

    if not subject and not body:
        return {"status": "error", "message": "subject 또는 body 중 하나 이상이 필요합니다."}

    parts = []
    if subject:
        parts.append(f"subject={quote(subject)}")
    if body:
        parts.append(f"body={quote(body)}")
    query = "&".join(parts)

    mail_url = f"mailto:{quote(to)}?{query}" if to else f"mailto:?{query}"

    return {
        "status": "success",
        "mail_url": mail_url,
    }
