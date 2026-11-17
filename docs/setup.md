# คู่มือติดตั้งและตั้งค่า

คู่มือทีละขั้นสำหรับติดตั้งครั้งแรก ถ้าแค่อยากรันเร็ว ๆ ดูหัวข้อ "เริ่มใช้งานเร็ว" ใน [README.md](../README.md)

สารบัญ

1. [สิ่งที่ต้องมี](#สิ่งที่ต้องมี)
2. [เตรียม AionUi (pairing)](#เตรียม-aionui-pairing)
3. [ติดตั้ง Python และแพ็กเกจ](#ติดตั้ง-python-และแพ็กเกจ)
4. [ตั้งค่าตัวแปรสภาพแวดล้อม](#ตั้งค่าตัวแปรสภาพแวดล้อม)
5. [ใส่ session ครั้งแรก](#ใส่-session-ครั้งแรก)
6. [รัน gateway และทดสอบ](#รัน-gateway-และทดสอบ)
7. [รันหน้าเว็บ](#รันหน้าเว็บ)
8. [ติดตั้ง MCP server](#ติดตั้ง-mcp-server)
9. [ใช้ Windows + WSL](#ใช้-windows--wsl)

---

## สิ่งที่ต้องมี

- AionUi ติดตั้งแล้ว และมี **Team** ที่ใช้งานในแอปได้จริง
- Python **3.10 ขึ้นไป** (เช็กด้วย `python --version`)
- เบราว์เซอร์ที่มี DevTools (Chrome / Edge / Firefox)
- Terminal (PowerShell บน Windows, Terminal บน macOS/Linux หรือ Ubuntu บน WSL)
- ถ้าจะใช้ MCP กับ Claude Desktop: ติดตั้ง Claude Desktop แล้ว

## เตรียม AionUi (pairing)

1. ติดตั้ง AionUi จาก https://www.aionui.com/ หรือหน้า Releases https://github.com/iOfficeAI/AionUi/releases แนะนำเวอร์ชันล่าสุด
2. เปิดแอป แล้วลองพิมพ์คำถามหา Team ให้ตอบได้ก่อน ถ้าขั้นนี้ยังไม่นิ่ง การต่อเว็บจะหาต้นเหตุยากมาก
3. เปิดโหมด WebUI ในแอป (Settings > WebUI ชื่ออาจต่างตามเวอร์ชัน) แล้วจด **พอร์ต** (ตัวอย่างในเอกสารใช้ `25808`)
4. เปิดเบราว์เซอร์ไปที่ `http://127.0.0.1:25808` จะเจอหน้า **Connect to AionUi Desktop WebUI**
   - ไม่มี username/password ใช้ **pairing code** แทน
   - รหัสแสดงในแอปเดสก์ท็อป เช่น `ABCD-12` และหมดอายุเร็ว (ประมาณ 1 นาที)
   - พิมพ์รหัสแล้วกด **Pair** จากนั้นต้องกดอนุมัติในหน้าต่างยืนยันบนเดสก์ท็อป
5. หลัง pair สำเร็จ ลองคุยกับ Team ผ่านหน้า WebUI ให้ได้ก่อน

pairing ต้องมีคนกดอนุมัติบนเดสก์ท็อป gateway จึง pair เองไม่ได้ วิธีที่ใช้คือ pair ด้วยมือในเบราว์เซอร์ แล้วเอา session ที่ได้ให้ gateway ใช้ซ้ำ (หัวข้อ "ใส่ session ครั้งแรก")

## ติดตั้ง Python และแพ็กเกจ

ติดตั้ง Python ถ้ายังไม่มี

- **Windows:** https://www.python.org/downloads/ ตอนติดตั้งติ๊ก "Add python.exe to PATH"
- **Ubuntu / WSL:** `sudo apt install -y python3 python3-venv python3-pip`
- **macOS:** `brew install python`

สร้าง virtual environment ที่รากโปรเจกต์ แล้วติดตั้งแพ็กเกจ

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -c "import fastapi, uvicorn, httpx, websockets, mcp; print('ok')"
```

ต้องเห็นคำว่า `ok` ถ้า PowerShell ฟ้องว่ารันสคริปต์ไม่ได้ ให้รัน `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` หนึ่งครั้ง แล้ว activate ใหม่ ทุกครั้งที่เปิด terminal ใหม่ต้อง activate venv ก่อน

## ตั้งค่าตัวแปรสภาพแวดล้อม

ตัวแปรทั้งหมดอยู่ใน [`.env.example`](../.env.example) คัดลอกเป็น `.env` แล้วแก้ค่า ส่วนวิธีโหลดเข้า terminal ดูใน [README.md](../README.md)

| ตัวแปร | จำเป็น | ความหมาย | ค่าตั้งต้น |
|---|---|---|---|
| `AION_BASE` | ใช่ | ที่อยู่ WebUI ของ AionUi | `http://127.0.0.1:25808` |
| `AION_TEAM_ID` | ใช่ | id ของ Team | ดูด้านล่าง |
| `AION_LEAD_CONVERSATION_ID` | ใช่ | id conversation ของ lead ใช้อ่านคำตอบ | ดูด้านล่าง |
| `ALLOWED_ORIGIN` | เมื่อใช้เว็บ | ที่อยู่ที่เปิดหน้าเว็บ ต้องตรงตัวอักษรต่อตัวอักษร | `http://localhost:5500` |
| `AION_MAX_WAIT` | ไม่ | รอคำตอบของทีมนานสุดกี่วินาที | `300` |
| `AION_IDLE_GRACE` | ไม่ | หลังรอบงานจบ ทุกสมาชิกต้องว่างต่อเนื่องกี่วินาที | `5` |
| `AION_ANSWER_MODE` | ไม่ | วิธีเลือกคำตอบจากข้อความของ lead (`smart` / `longest` / `last` / `all`) | `smart` |
| `AION_PING_MINUTES` | ไม่ | เช็ก session ทุกกี่นาที (0 = ปิด) | `10` |
| `AION_WARN_HOURS` | ไม่ | เตือนเมื่อ cookie เหลือน้อยกว่ากี่ชั่วโมง | `24` |
| `AION_REFRESH_MARGIN_HOURS` | ไม่ | ต่ออายุล่วงหน้าเมื่อโทเค็นเหลือน้อยกว่ากี่ชั่วโมง | `24` |
| `AION_WS_URL` | ไม่ | ที่อยู่ WebSocket ถ้าไม่ใช่ `AION_BASE` + `/ws` | อนุมานจาก `AION_BASE` |
| `AION_SESSION_FILE` | ไม่ | ที่เก็บไฟล์ session | `session_state.json` ที่รากโปรเจกต์ |
| `MCP_MODE`, `MCP_PORT` | ไม่ | โหมดของ MCP server (`stdio` / `http`) และพอร์ตโหมด http | `stdio`, `8001` |

ค่าตั้งต้นของ `AION_TEAM_ID` และ `AION_LEAD_CONVERSATION_ID` ในโค้ดเป็นค่าของเครื่องผู้เขียนเดิม ต้องตั้งของคุณเองเสมอ

### หา Team ID และ Lead Conversation ID

เปิด DevTools (F12) แท็บ **Network** ในหน้า WebUI ที่ pair แล้ว

- **Team ID:** ส่งข้อความหา Team หนึ่งข้อความ จะมี request `POST /api/teams/<id>/messages` ส่วน `<id>` คือ Team ID (รหัสภายใน ไม่ใช่ความลับระดับรหัสผ่าน)
- **Lead Conversation ID:** Team มีหลาย conversation (lead หนึ่งคน และสมาชิกอีกหลายคน) คำตอบสุดท้ายอยู่ใน conversation ของ **lead** ตอนเปิดหน้าแชตของทีมจะมี request `GET /api/conversations/<id>/messages?limit=200&content_mode=compact` ส่วน `<id>` คือค่าที่ต้องการ ถ้าเปิดหลายแท็บให้เลือกแท็บที่เป็น lead

## ใส่ session ครั้งแรก

gateway ต้องใช้ 3 อย่างจาก session ที่ pair แล้ว: **Cookie**, **CSRF token** และ **refresh token** (ตัวสุดท้ายทำให้ต่ออายุเองได้ ดู [session.md](session.md)) เก็บลงไฟล์ `session_state.json` ด้วยสคริปต์ ไม่ต้องตั้งผ่าน env

1. pair กับ WebUI ให้สำเร็จ (หัวข้อ "เตรียม AionUi")
2. **refresh token:** ใน Console ของหน้า WebUI รันโค้ดนี้หนึ่งครั้ง

   ```js
   fetch('/api/auth/refresh', {
     method: 'POST', credentials: 'include',
     headers: { 'x-csrf-token': decodeURIComponent(document.cookie.match(/aionui-csrf-token=([^;]+)/)?.[1] ?? '') }
   }).then(r => console.log('status', r.status))
   ```

   ต้องได้ `status 200` จากนั้นแท็บ **Network** > คลิก request `refresh` > แท็บ **Response** จะเห็น `refresh_token` ให้ copy ค่านั้น (คำสั่งนี้ออกโทเค็นชุดใหม่ ดังนั้น **ทำข้อ 3 ต่อทันที** อย่าทิ้งช่วง)
3. **Cookie และ CSRF:** คลิก request ใดก็ได้ที่ไปหา WebUI (เช่น `/api/...`) > Headers > Request Headers แล้ว copy
   - **Cookie** ทั้งบรรทัด (หน้าตา `ชื่อ1=ค่า1; ชื่อ2=ค่า2`)
   - **x-csrf-token**
4. รัน `python scripts/update_session.py` แล้ววางทั้งสามค่าตามที่ถาม (กด Enter ข้ามตัวที่ไม่เปลี่ยน)
5. ตรวจด้วย `python scripts/update_session.py --status` ต้องเห็น "refresh cookie (ต่ออายุเองได้): มี"

> Cookie และโทเค็นเทียบเท่ารหัสผ่านของ AionUi ใครได้ไปคุมแอปคุณได้ทั้งหมด ห้าม commit ขึ้น Git ห้ามแปะลงแชตหรือส่งให้ใคร ถ้าจะส่งตัวอย่าง request ให้ใคร (รวมถึงให้ AI ช่วย) ให้ลบค่าเหล่านี้แล้วใส่ `xxx` แทน

ถ้าไม่เห็นหัวข้อ Cookie แต่เห็น `Authorization: Bearer ...` แปลว่า session อยู่ใน header นั้นแทน ต้องแก้ `make_client()` ใน `src/gateway.py` ให้แนบ header ตัวนั้น

## รัน gateway และทดสอบ

ตอนที่ activate venv และโหลดตัวแปรแล้ว ที่รากโปรเจกต์

```bash
uvicorn gateway:app --app-dir src --host 127.0.0.1 --port 8000
```

เห็นข้อความทำนอง `Uvicorn running on http://127.0.0.1:8000` แปลว่าสำเร็จ ปล่อยหน้าต่างนี้ไว้ แล้วเปิด terminal ใหม่ทดสอบ

**ทดสอบที่ 1: health check** เปิด `http://127.0.0.1:8000/health` ต้องเห็น `{"ok": true}`

**ทดสอบที่ 2: ยิง /ask ตรง ๆ** (ก่อนต่อหน้าเว็บ)

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"สวัสดี ช่วยแนะนำตัวหน่อย"}'
```
```powershell
# Windows PowerShell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/ask `
  -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes('{"question":"สวัสดี ช่วยแนะนำตัวหน่อย"}'))
```

ต้องได้ `{"answer": "..."}` ก่อนค่อยไปขั้นถัดไป ถ้าได้ error ดู [troubleshooting.md](troubleshooting.md)

## รันหน้าเว็บ

1. เช็ก `GATEWAY_URL` ใน `web/index.html` ว่าตรงกับ gateway ของคุณ (ค่าตั้งต้น `http://127.0.0.1:8000/ask`)
2. เปิด terminal ใหม่ที่รากโปรเจกต์ แล้วรัน web server ง่าย ๆ

   ```bash
   python -m http.server 5500 --directory web
   ```

   ต้องเปิดผ่าน server แบบนี้ ไม่ใช่ดับเบิลคลิก `index.html` ไม่งั้นเบราว์เซอร์มี origin เป็น `null` แล้วติด CORS
3. เปิด `http://localhost:5500` พิมพ์คำถาม กด **ส่งคำถาม** (หรือ Ctrl+Enter) แล้วรอคำตอบ

`ALLOWED_ORIGIN` ต้องตรงกับที่อยู่ที่เปิดหน้าเว็บ **ตัวอักษรต่อตัวอักษร** เช่น เปิดที่ `http://localhost:5500` ก็ต้องตั้งเป็น `http://localhost:5500` (ไม่ใช่ `127.0.0.1:5500`) และถ้าแก้ต้องรีสตาร์ท gateway

## ติดตั้ง MCP server

ทำเมื่ออยากให้ Claude หรือ MCP client อื่นเรียก Team ได้ ต้องผ่านหัวข้อ "รัน gateway และทดสอบ" มาก่อน เพราะ `mcp_server.py` ใช้โค้ดคุยกับ AionUi ตัวเดียวกับ gateway และอ่าน session จาก `session_state.json` ไฟล์เดียวกัน

### โหมด stdio (client ในเครื่องเดียวกัน)

ทดสอบก่อนว่ารันได้ (จะค้างรอ input ซึ่งเป็นเรื่องปกติ กด Ctrl+C ออก)

```bash
python src/mcp_server.py
```

เพิ่มใน config ของ Claude Desktop (Windows: `%APPDATA%\Claude\claude_desktop_config.json`, macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "aionui-team": {
      "command": "C:\\path\\to\\project\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\project\\src\\mcp_server.py"],
      "env": {
        "AION_BASE": "http://127.0.0.1:25808",
        "AION_TEAM_ID": "id ของ Team",
        "AION_LEAD_CONVERSATION_ID": "id conversation ของ lead"
      }
    }
  }
}
```

ไม่ต้องใส่ cookie ใน config เพราะ MCP server อ่าน session จากไฟล์ (ต่ออายุเองและใช้ร่วมกับ gateway ได้) แก้ path ให้ตรงกับเครื่องคุณ แล้ว **ปิดและเปิด Claude Desktop ใหม่ทั้งโปรแกรม** จะเห็น tool `ask_team`

กรณี Claude Desktop อยู่บน Windows แต่ Python อยู่ใน WSL

```json
{
  "mcpServers": {
    "aionui-team": {
      "command": "wsl",
      "args": ["bash", "-lc",
        "cd ~/project && source .venv/bin/activate && AION_BASE=http://127.0.0.1:25808 AION_TEAM_ID='id ของ Team' AION_LEAD_CONVERSATION_ID='id conversation ของ lead' python src/mcp_server.py"]
    }
  }
}
```

ถ้าใช้ Claude Code (ตั้งตัวแปรให้ครบก่อน และใช้ python ใน venv)

```bash
claude mcp add aionui-team -- python /path/to/project/src/mcp_server.py
```

### โหมด HTTP (ไม่มีโทเค็น ใช้ในเครื่องเท่านั้น)

```bash
MCP_MODE=http python src/mcp_server.py      # PowerShell: $env:MCP_MODE="http"; python src/mcp_server.py
```

server อยู่ที่ `http://127.0.0.1:8001/mcp` และผูกกับ `127.0.0.1` เท่านั้น เพราะไม่มีการยืนยันตัวตน **อย่าเปิดออกอินเทอร์เน็ต**

งานที่ Team ทำอาจใช้เวลาหลายนาที และบาง MCP client มี timeout ของตัวเอง ถ้าถูกตัดกลางทาง ให้ปรับ timeout ฝั่ง client หรือแตกงานให้เล็กลง

## ใช้ Windows + WSL

ปัญหาที่เจอบ่อยคือ AionUi กับ gateway อยู่คนละฝั่ง (Windows กับ WSL) แล้ว `127.0.0.1` ไม่ได้ชี้ไปเครื่องเดียวกัน

**วิธีที่ง่ายที่สุด:** รันทุกอย่างฝั่งเดียวกัน ถ้า AionUi เป็นแอป Windows ก็รัน gateway ด้วย Python บน Windows (PowerShell)

**ถ้าต้องแยกฝั่ง (AionUi บน Windows, gateway ใน WSL)**

1. หา IP ของ Windows host จากใน WSL แล้วตั้ง `AION_BASE=http://<ip>:25808`

   ```bash
   ip route show | grep -i default | awk '{ print $3 }'
   ```
2. WebUI ของ AionUi ต้องยอมรับการเชื่อมต่อจากภายนอก `127.0.0.1` ของ Windows (ดู WebUI Settings) และ Windows Firewall ต้องไม่บล็อกพอร์ตนั้น
3. ทางเลือก: บน Windows 11 เปิด mirrored networking โดยสร้าง `%UserProfile%\.wslconfig`

   ```ini
   [wsl2]
   networkingMode=mirrored
   ```

   แล้วรัน `wsl --shutdown` และเปิด WSL ใหม่ หลังจากนั้น `127.0.0.1` ใช้ร่วมกันได้

ฝั่งเบราว์เซอร์บน Windows เข้า gateway ที่รันใน WSL ผ่าน `http://localhost:8000` ได้ตามปกติ
