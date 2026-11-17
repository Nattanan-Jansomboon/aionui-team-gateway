"""
MCP server (เวอร์ชัน DEMO ไม่มี token): เปิด Team ใน AionUi เป็น tool ชื่อ ask_team

อยู่โฟลเดอร์เดียวกับ gateway.py (ใช้ make_client / aion_ask_team ร่วมกัน)
session (cookie + CSRF) อ่านจาก session_state.json ที่รากโปรเจกต์ ใส่ด้วย scripts/update_session.py

รัน (จากรากโปรเจกต์):
    # โหมด stdio (client ในเครื่อง เช่น Claude Desktop / Claude Code)
    python src/mcp_server.py

    # โหมด HTTP (ไม่มีการตรวจ token ใช้ในเครื่องเท่านั้น)
    MCP_MODE=http python src/mcp_server.py   # http://127.0.0.1:8001/mcp

ตัวอย่างตั้งใน Claude Desktop (claude_desktop_config.json):
    {
      "mcpServers": {
        "aionui-team": {
          "command": "python",
          "args": ["/path/to/โปรเจกต์/src/mcp_server.py"],
          "env": {
            "AION_BASE": "http://127.0.0.1:25808",
            "AION_TEAM_ID": "id ของ Team",
            "AION_LEAD_CONVERSATION_ID": "id conversation ของ lead"
          }
        }
      }
    }
"""

import asyncio
import os

import httpx
import websockets
try:
    from mcp.server.mcpserver import MCPServer as FastMCP  # mcp 2.x (เปลี่ยนชื่อจาก FastMCP)
except ModuleNotFoundError:
    from mcp.server.fastmcp import FastMCP  # mcp 1.x

from gateway import AION_MAX_WAIT, SessionExpired, aion_ask_team, make_client

MCP_MODE = os.environ.get("MCP_MODE", "stdio")
MCP_PORT = int(os.environ.get("MCP_PORT", "8001"))

mcp = FastMCP("aionui-team")


@mcp.tool()
async def ask_team(question: str) -> str:
    """ส่งคำถามหรืองานให้ Team ใน AionUi แล้วรอคำตอบรวมของทีม

    ใช้เมื่อต้องการให้ทีมหลาย agent ช่วยกันคิด อาจใช้เวลาหลายนาที
    """
    question = question.strip()
    if not question:
        return "ไม่มีคำถามให้ส่ง"
    if len(question) > 2000:
        return "คำถามยาวเกิน 2000 ตัวอักษร ช่วยย่อให้สั้นลง"

    try:
        async with make_client() as client:
            return await asyncio.wait_for(aion_ask_team(client, question), timeout=AION_MAX_WAIT + 30)
    except NotImplementedError as e:
        return f"ยังใช้ไม่ได้: {e} (ต้องเติม TODO ใน gateway.py ก่อน)"
    except RuntimeError as e:
        return f"ตั้งค่าไม่ครบหรือ AionUi ไม่รับข้อความ: {e}"
    except SessionExpired as e:
        return (
            f"session ของ AionUi ใช้ไม่ได้: {e}"
            + ("" if "update_session.py" in str(e) else " (pair ใหม่แล้วรัน python scripts/update_session.py ไม่ต้องรีสตาร์ท)")
        )
    except asyncio.TimeoutError:
        return "Team ใช้เวลานานเกินไป ลองแบ่งงานให้เล็กลง"
    except (httpx.HTTPError, websockets.exceptions.WebSocketException, OSError):
        return "ติดต่อ AionUi ไม่ได้ เช็กว่า WebUI เปิดอยู่และ AION_BASE ถูกต้อง"


if __name__ == "__main__":
    if MCP_MODE == "http":
        import uvicorn

        # ผูกกับ 127.0.0.1 เท่านั้น เพราะไม่มีการยืนยันตัวตน
        uvicorn.run(mcp.streamable_http_app(), host="127.0.0.1", port=MCP_PORT)
    else:
        mcp.run()
