"""
update_session.py: ต่ออายุ session ของ AionUi โดยไม่ต้องรีสตาร์ท gateway หรือ MCP server

ขั้นตอนเมื่อ session หมดอายุ
  1. เปิด WebUI ในเบราว์เซอร์ แล้ว pair ใหม่ (ใส่ pairing code และกดยืนยันบนเดสก์ท็อป)
  2. กด F12 > Network > คลิก request ใดก็ได้ที่ไปหา WebUI > Request Headers
     copy ค่าของ Cookie (ทั้งบรรทัด) และ x-csrf-token
  3. รัน (จากรากโปรเจกต์):  python scripts/update_session.py   แล้ววางค่าตามที่ถาม

ดูสถานะ (ไม่แสดงค่าลับ):  python scripts/update_session.py --status
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # หา session_store ใน src/

from session_store import SESSION_FILE, store  # noqa: E402


def show_status():
    store.refresh_from_disk()
    print(f"ไฟล์ session: {SESSION_FILE}")
    print(f"จำนวน cookie: {len(store.cookies)}  ({', '.join(store.cookies) or 'ไม่มี'})")
    print(f"CSRF token: {'มี' if store.csrf_token() else 'ไม่มี'}")
    print(f"refresh cookie (ต่ออายุเองได้): {'มี' if store.has_refresh_token() else 'ไม่มี'}")
    if store.last_refresh_at:
        print(f"ต่ออายุสำเร็จล่าสุด: {datetime.fromtimestamp(store.last_refresh_at).isoformat(timespec='seconds')}")
    info = store.expiry_info()
    if not info:
        print("วันหมดอายุ: อ่านไม่ได้จากค่าที่มี (cookie ไม่ใช่ JWT และเซิร์ฟเวอร์ไม่ได้ระบุ)")
    for name, v in info.items():
        left = v["seconds_left"]
        txt = "หมดอายุแล้ว" if left <= 0 else f"เหลือ {left // 86400} วัน {left % 86400 // 3600} ชั่วโมง"
        print(f"  {name}: หมดอายุ {v['expires_at']}  ({txt})")


def main():
    if "--status" in sys.argv:
        show_status()
        return
    print(__doc__.split("ขั้นตอน")[0].strip())
    print()
    cookie = input("วาง Cookie ทั้งบรรทัด (Enter = ไม่เปลี่ยน): ").strip()
    if cookie.lower().startswith("cookie:"):
        cookie = cookie[7:].strip()
    cookie = cookie.strip("'\"")
    if cookie and "=" not in cookie:
        print("ค่าที่วางไม่ใช่รูปแบบ Cookie (ต้องมี ชื่อ=ค่า) ยกเลิก")
        return
    csrf = input("วาง x-csrf-token (Enter = ไม่เปลี่ยน): ").strip().strip("'\"")
    print("aionui-refresh เป็น HttpOnly และจำกัด Path จึงไม่อยู่ในบรรทัด Cookie ของ Network tab\n"
          "  หาได้จาก DevTools > Application > Cookies (ถ้าไม่เห็น ให้เรียก POST /api/auth/refresh หนึ่งครั้งก่อน)\n"
          "  หรือ Network tab > request /api/auth/refresh > Request Headers > Cookie")
    refresh = input("วาง ค่า aionui-refresh (Enter = ไม่เปลี่ยน): ").strip().strip("'\"")
    if refresh.lower().startswith("aionui-refresh="):
        refresh = refresh.split("=", 1)[1]
    if not cookie and not csrf and not refresh:
        print("ไม่มีอะไรเปลี่ยน")
        return
    store.set_credentials(cookie or None, csrf or None, refresh or None)
    print("\nบันทึกแล้ว gateway และ MCP จะใช้ค่าใหม่ในคำขอถัดไป (ไม่ต้องรีสตาร์ท)\n")
    show_status()


if __name__ == "__main__":
    main()
