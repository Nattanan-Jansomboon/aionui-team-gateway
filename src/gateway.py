"""
Gateway (เวอร์ชัน DEMO ไม่มี API key):
เว็บ -> (POST /ask) -> gateway นี้ -> AionUi WebUI (Team) -> กลับมาที่เว็บ

รัน (จากรากโปรเจกต์ ดูตัวแปรทั้งหมดที่ .env.example และ docs/setup.md):
    pip install -r requirements.txt
    export AION_BASE=http://127.0.0.1:25808
    export AION_TEAM_ID='id ของ Team (อยู่ใน URL /api/teams/<id>/messages)'
    export AION_LEAD_CONVERSATION_ID='id conversation ของ lead'
    export ALLOWED_ORIGIN=http://localhost:5500      # ที่อยู่ของหน้าเว็บ
    python scripts/update_session.py                 # ใส่ session ครั้งแรก (cookie + CSRF + refresh token)
    uvicorn gateway:app --app-dir src --host 127.0.0.1 --port 8000

หมายเหตุ:
- ไม่มีการตรวจ key ใด ๆ ใช้ทดสอบในเครื่องเท่านั้น ห้ามเปิดออกอินเทอร์เน็ต
- session (cookie + CSRF token + refresh token) เก็บใน session_state.json ผ่าน session_store.py
  gateway ต่ออายุเองด้วย /api/auth/refresh (ดู docs/session.md) ดูสถานะที่ GET /session/status
- AionUi Desktop ใช้ pairing code แทน username/password เราจึง pair ด้วยมือในเบราว์เซอร์ครั้งเดียว
  แล้วเอา session ที่ได้มาให้ gateway ใช้ซ้ำ
- API ภายในของ AionUi ไม่มีเอกสารทางการ โค้ดนี้เขียนตาม request จริงที่เห็นใน DevTools (ดู docs/how-it-works.md)
"""

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from collections import defaultdict

import httpx
import websockets
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from session_store import REFRESH_PATH, jwt_exp, store

AION_BASE = os.environ.get("AION_BASE", "http://127.0.0.1:25808")
AION_TEAM_ID = os.environ.get("AION_TEAM_ID", "01a13a38-487c-7a43-a996-2f5f3c7a2510")
# id ของ conversation ฝั่ง lead (ดูจาก URL /api/conversations/<id>/messages ใน DevTools)
AION_LEAD_CONVERSATION_ID = os.environ.get("AION_LEAD_CONVERSATION_ID", "d472378e")
AION_MAX_WAIT = int(os.environ.get("AION_MAX_WAIT", "300"))            # รอคำตอบของทีมได้นานสุด (วินาที)
# ถ้า runCompleted แล้ว ทุก agent ต้องว่าง (idle) ต่อเนื่องเท่านี้ (วินาที) ถึงถือว่าจบจริง
AION_IDLE_GRACE = float(os.environ.get("AION_IDLE_GRACE", "5"))
AION_WS_URL = os.environ.get("AION_WS_URL", AION_BASE.replace("http", "ws", 1) + "/ws")
# เช็กสถานะ session ทุกกี่นาที (0 = ปิด) และเตือนล่วงหน้ากี่ชั่วโมงก่อน cookie หมดอายุ
AION_PING_MINUTES = float(os.environ.get("AION_PING_MINUTES", "10"))
AION_WARN_HOURS = float(os.environ.get("AION_WARN_HOURS", "24"))
# วิธีเลือกคำตอบจากข้อความของ lead: smart | longest | last | all (ดู pick_answer)
AION_ANSWER_MODE = os.environ.get("AION_ANSWER_MODE", "smart").strip().lower()
# ต่ออายุ session ล่วงหน้าเมื่อ JWT เหลือน้อยกว่ากี่ชั่วโมง
AION_REFRESH_MARGIN_HOURS = float(os.environ.get("AION_REFRESH_MARGIN_HOURS", "24"))
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "http://localhost:5500")

@asynccontextmanager
async def lifespan(_app):
    task = asyncio.create_task(_keepalive_loop()) if AION_PING_MINUTES > 0 else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="AionUi Team gateway (demo)", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# ---------- จำกัดจำนวนครั้ง (กันยิงรัวจนเปลือง token) ----------

_hits: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 10  # ครั้งต่อนาที ต่อ IP


def rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    recent = [t for t in _hits[ip] if now - t < 60]
    if len(recent) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="ส่งถี่เกินไป ลองใหม่อีกสักครู่")
    recent.append(now)
    _hits[ip] = recent


# ---------- ส่วนที่คุยกับ AionUi ----------

class SessionExpired(Exception):
    """session ของ AionUi ไม่มี/หมดอายุ ต้อง pair ใหม่ แล้วรัน python scripts/update_session.py (ไม่ต้องรีสตาร์ท)"""


async def _capture_session(response: httpx.Response):
    """ถ้า AionUi ส่ง Set-Cookie กลับมา (ต่ออายุ session) เก็บค่าใหม่และบันทึกลงไฟล์ให้เอง"""
    store.update_from_response(response)


def make_client() -> httpx.AsyncClient:
    """สร้าง HTTP client ที่แนบ session ล่าสุด (อ่านจาก session_store ทุกครั้ง จึงได้ค่าใหม่โดยไม่ต้องรีสตาร์ท)"""
    cookie = store.cookie_header()
    if not cookie:
        raise SessionExpired(
            "ยังไม่มี session (pair แล้วรัน python scripts/update_session.py หรือตั้ง AION_SESSION_COOKIE)"
        )
    headers = {
        "Cookie": cookie,
        # เบราว์เซอร์ส่ง Origin/Referer ของหน้า WebUI ไปด้วย AionUi อาจตรวจสองตัวนี้
        # ตั้ง AION_BASE ให้ตรงกับที่อยู่ที่ใช้เปิด WebUI ในเบราว์เซอร์ (เช่น localhost vs 127.0.0.1)
        "Origin": AION_BASE,
        "Referer": AION_BASE + "/",
    }
    token = store.csrf_token()
    if token:
        headers["x-csrf-token"] = token
    client = httpx.AsyncClient(
        base_url=AION_BASE,
        timeout=30,
        headers=headers,
        event_hooks={"response": [_capture_session]},
    )
    client.aion_fp = store.fingerprint()  # session ที่ client นี้ใช้ (ไว้เช็กว่ามีใครต่ออายุไปแล้วไหม)
    return client


def _sync_headers(client: httpx.AsyncClient):
    """ยกค่า Cookie / CSRF ล่าสุดจาก store มาใส่ client (หลังต่ออายุ)"""
    client.headers["Cookie"] = store.cookie_header()
    token = store.csrf_token()
    if token:
        client.headers["x-csrf-token"] = token
    client.aion_fp = store.fingerprint()


async def refresh_session(seen_fp: str = None) -> bool:
    """ต่ออายุ session ด้วย POST /api/auth/refresh เหมือนที่หน้าเว็บของ AionUi ทำเมื่อเจอ 401

    - ต้องมี cookie aionui-refresh (HttpOnly, Path=/api/auth/refresh) ใน store
    - ใช้ file lock กัน gateway กับ MCP server refresh พร้อมกัน (refresh token อาจถูกเปลี่ยนทุกครั้ง)
    - ถ้า seen_fp ไม่ตรงกับ session ปัจจุบัน แปลว่าอีกโปรเซสต่ออายุไปแล้ว ไม่ต้องทำซ้ำ
    คืน True ถ้าตอนนี้มี session ใหม่ให้ใช้
    """
    lock = store.refresh_lock()
    await asyncio.to_thread(lock.acquire)
    try:
        store.refresh_from_disk()
        if seen_fp is not None and store.fingerprint() != seen_fp:
            return True
        if not store.has_refresh_token():
            _log.warning("[session] ไม่มี cookie aionui-refresh ต่ออายุเองไม่ได้ (ใส่ด้วย scripts/update_session.py)")
            return False
        headers = {
            "Cookie": store.cookie_header(REFRESH_PATH),
            "Origin": AION_BASE,
            "Referer": AION_BASE + "/",
        }
        token = store.csrf_token()
        if token:
            headers["x-csrf-token"] = token
        async with httpx.AsyncClient(base_url=AION_BASE, timeout=30) as c:
            # ส่ง refresh token ทั้งใน cookie (แบบเบราว์เซอร์) และ body (backend รองรับเป็นทางสำรอง)
            r = await c.post(REFRESH_PATH, headers=headers,
                             json={"refresh_token": store.cookies.get("aionui-refresh", "")})
        if r.status_code == 200:
            store.update_from_response(r)
            try:
                body = r.json()
            except ValueError:
                body = {}
            if isinstance(body, dict):
                body = body.get("data") if isinstance(body.get("data"), dict) and "token" in body["data"] else body
                store.apply_tokens(body.get("token"), body.get("refresh_token"))
            store.mark_refreshed()
            _log.info("[session] ต่ออายุสำเร็จ")
            return True
        _log.warning("[session] ต่ออายุไม่สำเร็จ (HTTP %s) ต้อง pair ใหม่", r.status_code)
        return False
    except (httpx.HTTPError, OSError, TimeoutError) as e:
        _log.warning("[session] ต่ออายุไม่สำเร็จ: %s", e)
        return False
    finally:
        lock.release()


async def request_with_refresh(client: httpx.AsyncClient, method: str, url: str, **kw) -> httpx.Response:
    """เรียก API ถ้าได้ 401/403 ให้ต่ออายุแล้วลองใหม่หนึ่งครั้ง"""
    r = await client.request(method, url, **kw)
    if r.status_code in (401, 403) and await refresh_session(getattr(client, "aion_fp", None)):
        _sync_headers(client)
        r = await client.request(method, url, **kw)
    return r


async def send_to_team(client: httpx.AsyncClient, question: str) -> dict:
    """ส่งข้อความเข้า Team (ยืนยันรูปแบบจาก DevTools แล้ว)

    POST /api/teams/{teamId}/messages
    body: {"content": "<ข้อความ>", "files": []}

    ตอบกลับทันทีเป็น "ใบรับเรื่อง" (enqueue_status = accepted) ยังไม่ใช่คำตอบของทีม
    คืนค่า data ที่มี message_id และ run.team_run_id
    """
    if not AION_TEAM_ID:
        raise RuntimeError("ยังไม่ได้ตั้ง AION_TEAM_ID (ดู README ขั้นที่ 5)")

    r = await request_with_refresh(
        client, "POST", f"/api/teams/{AION_TEAM_ID}/messages",
        json={"content": question, "files": []},
    )
    if r.status_code in (401, 403):
        raise SessionExpired(f"AionUi ตอบ {r.status_code}: {r.text[:300]}")
    r.raise_for_status()

    body = r.json()
    if not body.get("success"):
        raise RuntimeError(f"AionUi ไม่รับข้อความ: {body}")
    return body["data"]


def _content_text(item: dict) -> str:
    c = item.get("content")
    return c.get("content", "") if isinstance(c, dict) else ""


def analyze_history(items: list, baseline: int, question: str, user_ts=None):
    """วิเคราะห์ประวัติแชตของ lead หลังส่งข้อความ

    - baseline: created_at ล่าสุดก่อนส่ง (ใช้ตัดของเก่าทิ้ง ไม่พึ่งนาฬิกาเครื่อง)
    - หาข้อความของเรา (position == "right" และเนื้อหาตรงกับ question)
    - นับเฉพาะข้อความตอบของ lead (type == "text", position == "left",
      ไม่ใช่ข้อความที่ teammate ส่งมาให้ lead) ที่เกิดหลังข้อความของเรา
    คืน None ถ้ายังไม่เห็นข้อความของเราในประวัติ
    """
    new = [i for i in items if i.get("created_at", 0) > baseline and not i.get("hidden")]

    if user_ts is None:
        q = question.strip()
        for i in new:
            if (
                i.get("position") == "right"
                and i.get("type") == "text"
                and _content_text(i).strip() == q
            ):
                user_ts = i["created_at"]
                break
        if user_ts is None:
            return None

    after = [i for i in new if i.get("created_at", 0) > user_ts]
    lead_texts = [
        i
        for i in after
        if i.get("type") == "text"
        and i.get("position") == "left"
        and i.get("status") == "finish"
        and not (isinstance(i.get("content"), dict) and i["content"].get("teammate_message"))
    ]
    busy = any(i.get("status") != "finish" for i in after)
    # ลายนิ้วมือของสถานะ (ใช้ดีบัก/เทสต์ gateway ไม่ได้ใช้ตัดสินว่าจบ เพราะใช้ event WebSocket แทน)
    marker = (
        len(after),
        after[-1].get("id") if after else None,
        sum(1 for i in after if i.get("status") == "finish"),
    )
    return {"user_ts": user_ts, "lead_texts": lead_texts, "busy": busy, "marker": marker, "after": after}


def _is_teammate_msg(item: dict) -> bool:
    c = item.get("content")
    return isinstance(c, dict) and bool(c.get("teammate_message"))


def _smart_answer(after: list) -> str:
    """เลือกคำตอบจากลำดับเหตุการณ์หลังข้อความของเรา

    ข้อความ "ตอบโต้" (reactive) = ข้อความของ lead ที่พิมพ์ทันทีหลังได้รับข้อความจากสมาชิก
    โดยไม่มีการเรียกเครื่องมือคั่น (เช่น ตอบ idle notification ว่า "ไม่มีอะไรต้องทำ")
    ข้อความแบบนี้ถูกทิ้ง ยกเว้นยาวกว่าข้อความปกติที่ยาวที่สุด (กรณี lead สรุปคำตอบจริงตอนถูกปลุก)
    แล้วเลือกข้อความสุดท้ายที่เหลือ
    """
    normal, reactive_flag, entries = [], False, []
    for i in after:
        if _is_teammate_msg(i):
            reactive_flag = True
            continue
        if str(i.get("type", "")).startswith("tool"):
            reactive_flag = False
            continue
        if i.get("type") == "text" and i.get("position") == "left" and i.get("status") == "finish":
            t = _content_text(i).strip()
            if t:
                entries.append((t, reactive_flag))
                if not reactive_flag:
                    normal.append(t)
    if not entries:
        return ""
    cutoff = max((len(t) for t in normal), default=0)
    kept = [t for t, reactive in entries if not reactive or len(t) > cutoff]
    return (kept or [t for t, _ in entries])[-1]


def pick_answer(lead_texts: list, after: list = None) -> str:
    """เลือกคำตอบจากข้อความตอบของ lead หลายข้อความในรอบเดียว

    หลังทีมทำงานเสร็จ lead มักถูกปลุกซ้ำจาก idle notification ของสมาชิก แล้วพิมพ์ข้อความสั้น ๆ
    (เช่น "ไม่มีอะไรต้องทำ") ตามหลังคำตอบจริง ถ้าเอาข้อความสุดท้ายจะได้ข้อความขยะ
    AION_ANSWER_MODE:
      smart (ค่าตั้งต้น) = ทิ้งข้อความตอบโต้หลังสมาชิกส่งข้อความ แล้วเลือกข้อความสุดท้ายที่เหลือ (ดู _smart_answer)
      longest            = ข้อความที่ยาวที่สุด
      last               = ข้อความสุดท้าย (พฤติกรรมเดิม)
      all                = ทุกข้อความต่อกัน (ครบที่สุด แต่มีข้อความเล่าขั้นตอนปนมาด้วย)
    """
    texts = [t for t in (_content_text(i).strip() for i in lead_texts) if t]
    if not texts:
        return ""
    mode = AION_ANSWER_MODE
    if mode == "last":
        return texts[-1]
    if mode == "all":
        return "\n\n".join(texts)
    if mode == "smart" and after:
        return _smart_answer(after) or max(texts, key=len)
    return max(texts, key=len)


async def fetch_messages(client: httpx.AsyncClient) -> list:
    """GET /api/conversations/{leadId}/messages?limit=200&content_mode=compact"""
    r = await request_with_refresh(
        client, "GET", f"/api/conversations/{AION_LEAD_CONVERSATION_ID}/messages",
        params={"limit": 200, "content_mode": "compact"},
    )
    if r.status_code in (401, 403):
        raise SessionExpired(f"AionUi ตอบ {r.status_code}: {r.text[:300]}")
    r.raise_for_status()
    body = r.json()
    if not body.get("success"):
        raise RuntimeError(f"อ่านประวัติแชตไม่สำเร็จ: {body}")
    return body["data"]["items"]  # เรียงจากเก่า -> ใหม่


async def _open_ws():
    """เปิด WebSocket ของ AionUi (ยืนยันตัวตนด้วย Cookie ตอน handshake ไม่ต้องส่งเฟรมสมัคร)"""
    headers = {"Cookie": store.cookie_header()}
    try:
        return await websockets.connect(AION_WS_URL, additional_headers=headers, origin=AION_BASE)
    except TypeError:  # websockets เวอร์ชันเก่า
        return await websockets.connect(AION_WS_URL, extra_headers=headers, origin=AION_BASE)


def _event(raw):
    try:
        msg = json.loads(raw)
    except ValueError:
        return None, {}
    if not isinstance(msg, dict):
        return None, {}
    data = msg.get("data")
    return msg.get("name"), (data if isinstance(data, dict) else {})


FAILED_STATUSES = {"failed", "error", "cancelled", "canceled", "aborted"}


async def wait_for_run_done(ws, run_id: str) -> None:
    """รอสัญญาณจบรอบจาก WebSocket (ไม่เดาจากความเงียบของข้อความ)

    event ที่ใช้ (ยืนยันจาก ws_probe.py):
      - team.runCompleted {status: completed, team_run_id}   = รอบงานจบ
      - team.agentStatusChanged {status: working|idle, slot_id} = สถานะของสมาชิกแต่ละคน
    หลัง runCompleted lead อาจถูกปลุกอีกสั้น ๆ (เช่น รับรายงานสุดท้ายจาก teammate)
    จึงรอให้ทุกคน idle ต่อเนื่อง AION_IDLE_GRACE วินาทีก่อนถือว่าจบจริง
    (idle ชั่วคราวระหว่าง turn เกิดไม่ถึงวินาที ค่า 5 วินาทีกันได้)
    """
    slot_status: dict = {}
    run_done = False
    idle_since = None
    deadline = time.monotonic() + AION_MAX_WAIT

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise asyncio.TimeoutError()
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(0.5, remaining))
        except asyncio.TimeoutError:
            raw = None

        if raw is not None:
            name, data = _event(raw)
            if name == "team.agentStatusChanged" and data.get("slot_id"):
                slot_status[data["slot_id"]] = data.get("status")
            elif (
                isinstance(name, str)
                and name.startswith("team.run")
                and data.get("team_run_id") == run_id
            ):
                status = str(data.get("status", "")).lower()
                if status in FAILED_STATUSES:
                    raise RuntimeError(f"รอบงานของทีมจบแบบไม่สำเร็จ ({name}: {status})")
                if name == "team.runCompleted":
                    run_done = True

        working = any(s == "working" for s in slot_status.values())
        now = time.monotonic()
        if run_done and not working:
            if idle_since is None:
                idle_since = now
            elif now - idle_since >= AION_IDLE_GRACE:
                return
        else:
            idle_since = None


async def aion_ask_team(client: httpx.AsyncClient, question: str) -> str:
    """ส่งคำถามให้ Team แล้วรอจนได้คำตอบรวมของ lead

    ลำดับ:
      1) อ่านประวัติแชตของ lead เพื่อจดจุดเริ่มต้น (baseline)
      2) เปิด WebSocket ก่อนส่ง จะได้ไม่พลาด event
      3) POST /api/teams/{teamId}/messages แล้วจำ team_run_id จากใบรับเรื่อง
      4) รอ event team.runCompleted ของ run นั้น + ทุก agent idle ต่อเนื่อง (wait_for_run_done)
      5) อ่านประวัติแชตของ lead อีกครั้ง แล้วคืนข้อความตอบสุดท้ายของ lead
    """
    if not AION_LEAD_CONVERSATION_ID:
        raise RuntimeError("ยังไม่ได้ตั้ง AION_LEAD_CONVERSATION_ID (ดู README ขั้นที่ 5)")

    before = await fetch_messages(client)
    baseline = max((i.get("created_at", 0) for i in before), default=0)

    try:
        ws = await _open_ws()
    except websockets.exceptions.InvalidHandshake:  # เช่น 401/403 ตอน handshake: ลองต่ออายุแล้วต่อใหม่หนึ่งครั้ง
        if not await refresh_session(getattr(client, "aion_fp", None)):
            raise
        _sync_headers(client)
        ws = await _open_ws()
    try:
        receipt = await send_to_team(client, question)
        run_id = (receipt.get("run") or {}).get("team_run_id")
        if not run_id:
            raise RuntimeError("ใบรับเรื่องไม่มี team_run_id")
        await wait_for_run_done(ws, run_id)
    finally:
        await ws.close()

    # ข้อความล่าสุดอาจเขียนลงประวัติช้ากว่า event เล็กน้อย จึงลองอ่านซ้ำสองสามครั้ง
    for _ in range(10):
        items = await fetch_messages(client)
        st = analyze_history(items, baseline, question)
        if st and st["lead_texts"]:
            return pick_answer(st["lead_texts"], st["after"])
        await asyncio.sleep(1)
    raise RuntimeError("ทีมทำงานจบแล้ว แต่ไม่พบข้อความตอบของ lead ในประวัติแชต")


# ---------- endpoint ที่หน้าเว็บเรียก ----------

class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class AskOut(BaseModel):
    answer: str


@app.post("/ask", response_model=AskOut, dependencies=[Depends(rate_limit)])
async def ask(body: AskIn):
    try:
        async with make_client() as client:
            answer = await asyncio.wait_for(
                aion_ask_team(client, body.question), timeout=AION_MAX_WAIT + 30
            )
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except SessionExpired as e:
        raise HTTPException(status_code=401, detail=f"session ของ AionUi ใช้ไม่ได้: {e} (pair ใหม่ แล้วรัน python scripts/update_session.py)")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Team ใช้เวลานานเกินไป")
    except (httpx.HTTPError, websockets.exceptions.WebSocketException, OSError):
        raise HTTPException(status_code=502, detail="ติดต่อ AionUi ไม่ได้ (HTTP หรือ WebSocket)")
    return AskOut(answer=answer)


@app.get("/health")
async def health():
    return {"ok": True}


# ---------- ตรวจสถานะ session ----------

_log = logging.getLogger("uvicorn.error")
_last_ok = None
_warned: set = set()


async def check_session() -> dict:
    """ตรวจว่า session ยังใช้ได้ไหมด้วยคำขออ่านเบา ๆ (ไม่ส่งข้อความเข้าทีม) และรายงานวันหมดอายุ (ไม่เปิดเผยค่า cookie)"""
    result = {"ok": False, "reason": None, "expiry": store.expiry_info()}
    if not AION_LEAD_CONVERSATION_ID:
        result["reason"] = "ยังไม่ได้ตั้ง AION_LEAD_CONVERSATION_ID"
        return result
    try:
        async with make_client() as client:
            r = await request_with_refresh(
                client, "GET", f"/api/conversations/{AION_LEAD_CONVERSATION_ID}/messages",
                params={"limit": 1, "content_mode": "compact"},
            )
        if r.status_code == 200:
            result["ok"] = True
        elif r.status_code in (401, 403):
            result["reason"] = f"session หมดอายุหรือถูกปฏิเสธ (HTTP {r.status_code})"
        else:
            result["reason"] = f"AionUi ตอบ HTTP {r.status_code}"
    except SessionExpired as e:
        result["reason"] = str(e)
    except (httpx.HTTPError, OSError):
        result["reason"] = "ติดต่อ AionUi ไม่ได้"
    result["expiry"] = store.expiry_info()  # อาจเปลี่ยนหลังได้ Set-Cookie ใหม่
    return result


async def _keepalive_loop():
    """เช็ก session เป็นระยะ: เตือนเมื่อใช้ไม่ได้/ใกล้หมดอายุ (และถ้า AionUi ต่ออายุแบบเลื่อนวัน การเรียกนี้ช่วยต่ออายุด้วย)"""
    global _last_ok
    await asyncio.sleep(3)
    while True:
        try:
            # ต่ออายุล่วงหน้าเมื่อ JWT เหลือน้อยกว่า AION_REFRESH_MARGIN_HOURS
            exp = jwt_exp(store.cookies.get("aionui-session", ""))
            if exp and exp - time.time() < AION_REFRESH_MARGIN_HOURS * 3600:
                await refresh_session()
            res = await check_session()
            ok = res["ok"]
            if ok and _last_ok is not True:
                _log.info("[session] ใช้งานได้")
            if not ok and _last_ok is not False:
                _log.warning("[session] ใช้ไม่ได้: %s | ให้ pair ใหม่ แล้วรัน python scripts/update_session.py", res.get("reason"))
            _last_ok = ok
            for name, v in res["expiry"].items():
                hrs = v["seconds_left"] / 3600
                if 0 < hrs < AION_WARN_HOURS and (name, int(hrs)) not in _warned:
                    _warned.add((name, int(hrs)))
                    _log.warning("[session] cookie %s จะหมดอายุในอีก %.1f ชั่วโมง", name, hrs)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # ห้ามให้ลูปนี้ล้มจนหยุดตรวจ
            _log.warning("[session] ตรวจสอบไม่สำเร็จ: %s", e)
        await asyncio.sleep(max(AION_PING_MINUTES, 0.1) * 60)


@app.get("/session/status", dependencies=[Depends(rate_limit)])
async def session_status():
    return await check_session()
