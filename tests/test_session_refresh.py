"""ทดสอบการต่ออายุ session ด้วย mock server (ไม่แตะ AionUi จริง / ไม่แตะ session_state.json จริง)
รัน (จากรากโปรเจกต์): python tests/test_session_refresh.py
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # หา gateway ใน src/

tmp = tempfile.mkdtemp()
os.environ["AION_SESSION_FILE"] = os.path.join(tmp, "s.json")
os.environ["AION_SESSION_COOKIE"] = ""
os.environ["AION_CSRF_TOKEN"] = ""

import httpx  # noqa: E402

import gateway  # noqa: E402
from session_store import SessionStore  # noqa: E402

state = {"valid": "jwt-other",  # jwt-old หมดอายุแล้ว
 "refresh": "r1", "refresh_calls": 0, "seen_cookies": []}


def handler(request: httpx.Request) -> httpx.Response:
    cookies = request.headers.get("cookie", "")
    if request.url.path == "/api/auth/refresh":
        state["refresh_calls"] += 1
        assert "aionui-refresh=" + state["refresh"] in cookies, cookies
        import json as _json
        assert _json.loads(request.content)["refresh_token"] == state["refresh"]
        state["valid"], state["refresh"] = "jwt-new", "r2"
        if state.get("body_mode"):  # แบบจริงของ AionUi ที่เจอ: โทเค็นมาใน body ไม่มี Set-Cookie ของ session
            return httpx.Response(200, headers=[("set-cookie", "aionui-csrf-token=csrf-new; Path=/")],
                                  json={"success": True, "token": "jwt-new", "refresh_token": "r2"})
        return httpx.Response(200, headers=[
            ("set-cookie", "aionui-session=jwt-new; Path=/; HttpOnly"),
            ("set-cookie", "aionui-refresh=r2; Path=/api/auth/refresh; HttpOnly; Max-Age=999999"),
            ("set-cookie", "aionui-csrf-token=csrf-new; Path=/"),
        ], json={"success": True})
    state["seen_cookies"].append(cookies)
    assert "aionui-refresh" not in cookies, "refresh cookie รั่วไปยัง path อื่น"
    if f"aionui-session={state['valid']}" not in cookies:
        return httpx.Response(401, json={"success": False})
    return httpx.Response(200, json={"success": True, "data": {"items": []}, "csrf": request.headers.get("x-csrf-token")})


_Real = httpx.AsyncClient


def fake_client(*a, **kw):
    kw["transport"] = httpx.MockTransport(handler)
    return _Real(*a, **kw)


gateway.httpx.AsyncClient = fake_client


async def main():
    s = gateway.store
    s.set_credentials("aionui-session=jwt-old; aionui-csrf-token=csrf-old; rl_user_id=x", None, "r1")
    assert "rl_user_id" not in s.cookies, "ไม่ควรเก็บ cookie analytics"

    # 1) 401 -> refresh -> ส่งซ้ำสำเร็จ และได้ CSRF ใหม่
    async with gateway.make_client() as c:
        r = await gateway.request_with_refresh(c, "GET", "/api/conversations/x/messages")
        assert r.status_code == 200 and r.json()["csrf"] == "csrf-new", r.text
    assert state["refresh_calls"] == 1
    assert s.cookies["aionui-session"] == "jwt-new" and s.cookies["aionui-refresh"] == "r2"
    assert s.meta["aionui-refresh"]["path"] == "/api/auth/refresh"
    assert s.last_refresh_at

    # 2) อีก client ที่ถือ session เก่า (เหมือนโปรเซสที่สอง) ไม่ควร refresh ซ้ำ
    stale = _Real(base_url=gateway.AION_BASE, headers={"Cookie": "aionui-session=jwt-old"},
                  transport=httpx.MockTransport(handler))
    stale.aion_fp = "old-fingerprint"
    stale.headers["Cookie"] = "aionui-session=jwt-old"
    r = await gateway.request_with_refresh(stale, "GET", "/api/conversations/x/messages")
    assert r.status_code == 200 and state["refresh_calls"] == 1, state["refresh_calls"]

    # 3) ไฟล์ถูกโหลดใหม่โดยอีกโปรเซส (SessionStore ใหม่) ได้ค่าเดียวกัน
    s2 = SessionStore(os.environ["AION_SESSION_FILE"])
    assert s2.cookies["aionui-refresh"] == "r2" and s2.csrf_token() == "csrf-new"

    # 3.5) โทเค็นมาใน body อย่างเดียว (ไม่มี Set-Cookie ของ session/refresh)
    state.update(valid="jwt-other", body_mode=True, refresh_calls=0)
    async with gateway.make_client() as c:
        r = await gateway.request_with_refresh(c, "GET", "/api/conversations/x/messages")
        assert r.status_code == 200, r.text
    assert state["refresh_calls"] == 1 and s.cookies["aionui-session"] == "jwt-new"
    state["body_mode"] = False

    # 4) ไม่มี refresh cookie -> ต่ออายุไม่ได้ ได้ 401 กลับมาตรง ๆ
    s.cookies.pop("aionui-refresh"); s.save()
    state["valid"] = "something-else"
    async with gateway.make_client() as c:
        r = await gateway.request_with_refresh(c, "GET", "/api/conversations/x/messages")
        assert r.status_code == 401
    print("ผ่านทั้งหมด")


asyncio.run(main())
