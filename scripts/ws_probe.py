"""
ws_probe.py: แอบฟัง WebSocket ของ AionUi แล้วแสดงชื่อ event ทุกเฟรมที่ไหลมา
ใช้หาว่า AionUi ส่งสัญญาณ "ทีมทำงานเสร็จทั้งรอบ" ออกมาเป็น event ชื่ออะไร

วิธีใช้ (ตั้งตัวแปรเหมือนตอนรัน gateway):
    $env:AION_BASE = "http://localhost:25808"
    $env:AION_SESSION_COOKIE = "..."
    python scripts/ws_probe.py

จากนั้นไปส่งงานให้ทีมในหน้า WebUI (งานที่ให้สมาชิกช่วยกัน เช่น ให้ Data Analyst กับ
Report Writer ตอบคนละบรรทัดแล้วสรุป) รอจนทีมตอบเสร็จ แล้วกด Ctrl+C

ผลลัพธ์:
- หน้าจอ: เวลา + ชื่อ event + ฟิลด์สำคัญ (event team.sessionStatusChanged ถูกซ่อนไว้เพราะเกิดซ้ำบ่อย)
- ไฟล์ logs/ws_probe.log: ทุกเฟรมเต็ม ๆ บรรทัดละหนึ่งเฟรม (ค่าที่ชื่อมี token/cookie/password ถูกปิดเป็น ***)
  ในนั้นอาจมีเนื้อหาแชตด้วย ตรวจก่อนส่งให้ใคร
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import websockets

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))  # หา session_store ใน src/

BASE = os.environ.get("AION_BASE", "http://localhost:25808")
try:
    from session_store import store

    COOKIE = store.cookie_header()
except Exception:
    COOKIE = os.environ.get("AION_SESSION_COOKIE", "")
WS_URL = os.environ.get("AION_WS_URL", BASE.replace("http", "ws", 1) + "/ws")
LOG_FILE = str(_ROOT / "logs" / "ws_probe.log")  # logs/ ถูกกันออกจาก Git (มีเนื้อหาแชตของทีม)
HIDE_ON_SCREEN = {"team.sessionStatusChanged"}
BRIEF_KEYS = ("status", "state", "role", "type", "team_run_id", "slot_id", "conversation_id")
SECRET_WORDS = ("token", "cookie", "password", "secret")


def mask(obj):
    if isinstance(obj, dict):
        return {
            k: ("***" if any(w in k.lower() for w in SECRET_WORDS) else mask(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [mask(v) for v in obj]
    return obj


async def connect():
    headers = {"Cookie": COOKIE} if COOKIE else {}
    try:
        return await websockets.connect(WS_URL, additional_headers=headers, origin=BASE)
    except TypeError:  # websockets เวอร์ชันเก่า
        return await websockets.connect(WS_URL, extra_headers=headers, origin=BASE)


async def main():
    if not COOKIE:
        print("คำเตือน: ยังไม่ได้ตั้ง AION_SESSION_COOKIE อาจเชื่อมต่อไม่ได้")
    ws = await connect()
    print(f"เชื่อมต่อแล้ว: {WS_URL}  (กด Ctrl+C เพื่อหยุด)")
    shown = 0
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        async for raw in ws:
            now = time.strftime("%H:%M:%S")
            try:
                msg = json.loads(raw)
            except ValueError:
                print(now, "(ไม่ใช่ JSON)", str(raw)[:80])
                continue
            name = msg.get("name") if isinstance(msg, dict) else None
            data = msg.get("data") if isinstance(msg, dict) else None
            log.write(json.dumps({"t": now, "msg": mask(msg)}, ensure_ascii=False) + "\n")
            log.flush()
            if name in HIDE_ON_SCREEN:
                continue
            brief = {k: data[k] for k in BRIEF_KEYS if isinstance(data, dict) and k in data}
            print(now, name, brief)
            shown += 1


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nหยุดแล้ว ดูรายละเอียดทั้งหมดใน", LOG_FILE)
