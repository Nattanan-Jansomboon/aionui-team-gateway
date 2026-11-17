# AionUi Team Gateway

ใช้ Team ที่สร้างไว้ใน [AionUi](https://www.aionui.com/) จากข้างนอกแอปได้ 2 ทาง

1. **หน้าเว็บ** พิมพ์คำถามในเว็บ แล้วรอ Team ตอบ
2. **MCP** ให้ Claude หรือ MCP client อื่นเรียก Team เป็น tool ชื่อ `ask_team`

```
หน้าเว็บ (web/index.html) ──POST /ask──► gateway (src/gateway.py) ──REST + WebSocket──► AionUi WebUI ──► Team
MCP client ─────────────────MCP───────► mcp_server (src/mcp_server.py) ─(ใช้โค้ดของ gateway)─┘
```

โปรเจกต์นี้ใช้ในงาน AutoReview (สรุปความเห็นลูกค้าอัตโนมัติ) แต่ใช้กับ Team อื่นของ AionUi ได้เหมือนกัน

> **ใช้ในเครื่องเท่านั้น**
> gateway และ MCP server **ไม่มี API key** ใครเข้าถึงพอร์ตได้ก็สั่ง Team ได้ (และ Team เปลืองโทเค็น)
> รันที่ `127.0.0.1` เท่านั้น ห้ามเปิดออกอินเทอร์เน็ตหรือทำ tunnel
>
> API ภายในของ AionUi ไม่มีเอกสารทางการ และอาจเปลี่ยนตามเวอร์ชัน โค้ดเขียนตาม request ที่เห็นจริงใน DevTools

## โครงสร้างโปรเจกต์

```
.
├── README.md                 หน้านี้
├── requirements.txt          แพ็กเกจ Python
├── .env.example              ตัวอย่างตัวแปรสภาพแวดล้อม (ไม่มีค่าลับ)
├── .gitignore                กันค่าลับ ล็อก และโฟลเดอร์ในเครื่องออกจาก Git
│
├── src/                      โค้ดหลัก
│   ├── gateway.py            ตัวกลาง FastAPI: รับ /ask, คุยกับ AionUi, ต่ออายุ session เอง
│   ├── mcp_server.py         เปิด Team เป็น MCP tool (ใช้โค้ดของ gateway.py)
│   └── session_store.py      ที่เก็บ cookie / CSRF / refresh token ในไฟล์ session_state.json
│
├── scripts/                  เครื่องมือที่รันด้วยมือ
│   ├── update_session.py     ใส่ session ใหม่หลัง pair (และ --status ดูวันหมดอายุ)
│   └── ws_probe.py           ดู event ที่ AionUi ส่งทาง WebSocket (ใช้ตอน AionUi อัปเดตแล้วพัง)
│
├── web/
│   └── index.html            หน้าเว็บพิมพ์คำถาม
│
├── tests/                    เทสต์ (ไม่แตะ AionUi จริง)
│   ├── test_session_refresh.py
│   └── test_pick_answer.py
│
├── docs/                     เอกสารละเอียด (ดูตารางด้านล่าง)
│   └── team-workflow/        สเปกงานของ Team ใน AionUi และตัวอย่างรายงานรอบรัน
│
├── logs/                     ล็อกในเครื่อง   [ไม่ขึ้น Git]
└── session_state.json        session ของ AionUi  [ไม่ขึ้น Git, เทียบเท่ารหัสผ่าน]
```

## เริ่มใช้งานเร็ว

ต้องมี Python 3.10 ขึ้นไป และ AionUi ที่เปิด WebUI แล้ว มี Team ใช้งานได้ รายละเอียดทีละขั้นอยู่ที่ [docs/setup.md](docs/setup.md)

**1. ติดตั้ง** (ทำที่รากโปรเจกต์)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**2. ตั้งค่า** คัดลอก `.env.example` เป็น `.env` แล้วใส่ `AION_TEAM_ID` กับ `AION_LEAD_CONVERSATION_ID` (วิธีหาอยู่ใน [docs/setup.md](docs/setup.md#หา-team-id-และ-lead-conversation-id)) จากนั้นโหลดเข้า terminal

```bash
set -a; source .env; set +a        # Linux / macOS / WSL
```
```powershell
# Windows PowerShell
Get-Content .env | Where-Object { $_ -match '^\s*[^#\s]' } | ForEach-Object { $k,$v = $_ -split '=',2; Set-Item "env:$($k.Trim())" $v.Trim() }
```

**3. ใส่ session ของ AionUi** (ทำครั้งแรก และเมื่อต้อง pair ใหม่) pair ในเบราว์เซอร์ก่อน แล้วรัน

```bash
python scripts/update_session.py
```

**4. รัน gateway**

```bash
uvicorn gateway:app --app-dir src --host 127.0.0.1 --port 8000
```

ตรวจที่ `http://127.0.0.1:8000/health` ต้องได้ `{"ok": true}` และ `http://127.0.0.1:8000/session/status` บอกว่า session ใช้ได้ไหม

**5. เปิดหน้าเว็บ** (อีก terminal หนึ่ง)

```bash
python -m http.server 5500 --directory web
```

เปิด `http://localhost:5500` พิมพ์คำถาม แล้วกด **ส่งคำถาม** (หรือ Ctrl+Enter)

**MCP (ไม่บังคับ):** ดูวิธีตั้งค่ากับ Claude Desktop / Claude Code ใน [docs/setup.md](docs/setup.md#ติดตั้ง-mcp-server)

## เอกสารในโฟลเดอร์ docs

| ไฟล์ | อ่านเมื่อ |
|---|---|
| [docs/setup.md](docs/setup.md) | ติดตั้งครั้งแรก ตั้งค่าตัวแปร รันเว็บ ตั้ง MCP และการใช้ Windows + WSL |
| [docs/session.md](docs/session.md) | อยากรู้ว่า session ต่ออายุเองอย่างไร หรือ session หมดอายุแล้วต้องทำอะไร |
| [docs/how-it-works.md](docs/how-it-works.md) | อยากเข้าใจว่า gateway คุยกับ AionUi อย่างไร หรือ AionUi อัปเดตแล้วพัง |
| [docs/troubleshooting.md](docs/troubleshooting.md) | เจอ error (401, 502, 504 ฯลฯ) |
| [docs/team-workflow/](docs/team-workflow/README.md) | สเปกงานของ Team ใน AionUi (AutoReview) และตัวอย่างรายงานรอบรัน |

## ทดสอบโค้ด

```bash
python tests/test_session_refresh.py
python tests/test_pick_answer.py
```

เทสต์ใช้ mock server และไฟล์ session ชั่วคราว ไม่แตะ AionUi จริงและไม่แตะ `session_state.json` ของคุณ

## ก่อน push ขึ้น Git

- [ ] `session_state.json`, `.env`, `logs/` ไม่อยู่ในรายการไฟล์ที่จะ commit (`git status` ต้องไม่เห็น) ค่าเหล่านี้เทียบเท่ารหัสผ่านของ AionUi
- [ ] ไม่ได้วาง cookie หรือโทเค็นลงในไฟล์ใด ๆ รวมถึงเอกสารและโน้ต
- [ ] ตรวจ `docs/team-workflow/` ว่ามีอีเมลหรือรหัสโฟลเดอร์ Drive ที่ไม่อยากแชร์หรือไม่
- [ ] ค่าตั้งต้นของ `AION_TEAM_ID` และ `AION_LEAD_CONVERSATION_ID` ใน `src/gateway.py` เป็นค่าของเครื่องผู้เขียนเดิม เพื่อนร่วมทีมต้องตั้งของตัวเองเสมอ

## ข้อควรรู้

- gateway จำกัด 10 ครั้งต่อนาทีต่อ IP (แก้ที่ `RATE_LIMIT` ใน `src/gateway.py`) เก็บในหน่วยความจำ รีสตาร์ทแล้วนับใหม่
- โปรเจกต์พึ่ง API ภายในของ AionUi อัปเดตแอปแล้วอาจพัง ดูวิธีสำรวจใหม่ใน [docs/how-it-works.md](docs/how-it-works.md#เมื่อ-aionui-อัปเดตแล้วพัง)
- ถ้าวันหนึ่งจะเปิดให้คนอื่นนอกเครื่องใช้ ต้องเพิ่มการยืนยันตัวตน (API key) ก่อน
