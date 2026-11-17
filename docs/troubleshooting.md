# แก้ปัญหาที่เจอบ่อย

## รหัสตอบกลับของ `/ask`

| ผลลัพธ์ | ความหมาย | วิธีแก้ |
|---|---|---|
| `200` `{"answer": "..."}` | สำเร็จ | |
| `401` "session ของ AionUi ใช้ไม่ได้" | ยังไม่มี session หรือหมดอายุ และต่ออายุเองไม่ได้ | pair ใหม่ แล้วรัน `python scripts/update_session.py` (ดู [session.md](session.md)) |
| `429` | ส่งเกิน 10 ครั้ง/นาที | รอสักครู่ หรือปรับ `RATE_LIMIT` ใน `src/gateway.py` |
| `500` "ยังไม่ได้ตั้ง …" | ยังไม่ได้ตั้ง `AION_TEAM_ID` หรือ `AION_LEAD_CONVERSATION_ID` | ตั้งตาม [setup.md](setup.md#ตั้งค่าตัวแปรสภาพแวดล้อม) |
| `502` | ติดต่อ AionUi ไม่ได้ (HTTP หรือ WebSocket) | เปิด WebUI, เช็ก `AION_BASE`, ดูหัวข้อ WSL ใน [setup.md](setup.md#ใช้-windows--wsl) |
| `504` | ทีมใช้เวลานานเกิน `AION_MAX_WAIT` (ค่าตั้งต้น 300 วินาที) | ดูตารางด้านล่าง |

## อาการอื่น

| อาการ | สาเหตุที่เป็นไปได้ | วิธีแก้ |
|---|---|---|
| `ModuleNotFoundError` | ไม่ได้ activate venv | activate `.venv` แล้ว `pip install -r requirements.txt` ใหม่ |
| `ModuleNotFoundError: gateway` ตอนรัน `uvicorn` | รันโดยไม่มี `--app-dir src` หรือรันนอกรากโปรเจกต์ | `uvicorn gateway:app --app-dir src ...` ที่รากโปรเจกต์ |
| `ImportError ... streamable_http_app` | แพ็กเกจ `mcp` เก่าเกินไป | `pip install -U "mcp[cli]"` |
| `No module named 'mcp.server.fastmcp'` (mcp 2.x) | mcp 2.x เปลี่ยนชื่อ `FastMCP` เป็น `MCPServer` | ใช้ `src/mcp_server.py` เวอร์ชันนี้ที่รองรับทั้ง 1.x และ 2.x (หรือ `pip install "mcp<2"`) |
| เว็บขึ้น "ส่งคำถามไม่สำเร็จ: Failed to fetch" | gateway ไม่ได้รัน, `GATEWAY_URL` ผิด หรือติด CORS | เช็ก `GATEWAY_URL` ใน `web/index.html` เปิดผ่าน `http://localhost:5500` และ `ALLOWED_ORIGIN` ตรงเป๊ะ (ดู Console ประกอบ) |
| `504` ทั้งที่ทีมตอบแล้วในแอป | `AION_LEAD_CONVERSATION_ID` ผิดจึงไม่เห็นข้อความของเรา หรือไม่เห็น event `team.runCompleted` (ชื่อเปลี่ยนหลังอัปเดต AionUi) | เช็ก id ของ lead แล้วรัน `python scripts/ws_probe.py` ส่งงานทดสอบ ดูชื่อ event ตอนท้าย ([how-it-works.md](how-it-works.md#เมื่อ-aionui-อัปเดตแล้วพัง)) |
| ได้คำตอบเป็นข้อความระหว่างทาง (เช่น "กำลังรอ...") หรือข้อความขยะ ("ไม่มีอะไรต้องทำ") | lead ถูกปลุกอีกหลังช่วงรอ หรือเลือกคำตอบพลาด | เพิ่ม `AION_IDLE_GRACE` (เช่น 10) หรือลอง `AION_ANSWER_MODE=all` ([how-it-works.md](how-it-works.md#การเลือกคำตอบ-aion_answer_mode)) |
| `502` ทั้งที่ HTTP ปกติ | เชื่อม WebSocket ไม่ได้ (ถูกปฏิเสธหรือ URL ผิด) | รัน `python scripts/ws_probe.py` ถ้าต่อไม่ติด เช็ก `AION_WS_URL` และ session |
| ใส่ Cookie แล้ว WebSocket ยังต่อไม่ติด | WebSocket ต้องใช้ token แยก | ดูใน DevTools ว่า token มาจาก request ไหน แล้วส่งตามรูปแบบนั้น |
| `/session/status` ขึ้น `ok: false` | session หมดอายุหรือถูกปฏิเสธ | ต่ออายุเองไม่ได้ให้ pair ใหม่ตาม [session.md](session.md#เมื่อต้อง-pair-ใหม่-ทำเอง-ไม่ถึงนาที) |
| ภาษาไทยเพี้ยนตอนยิงด้วย PowerShell | encoding | ใช้ `Invoke-RestMethod` แบบระบุ UTF-8 ตามตัวอย่างใน [setup.md](setup.md#รัน-gateway-และทดสอบ) |
| Claude Desktop ไม่เห็น tool `ask_team` | config ผิด path หรือไม่ได้รีสตาร์ท | เช็ก path ใน JSON (ชี้ไป `src/mcp_server.py`) แล้วปิดเปิด Claude Desktop ใหม่ทั้งโปรแกรม |
