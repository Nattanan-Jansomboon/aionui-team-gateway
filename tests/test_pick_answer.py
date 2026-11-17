"""ทดสอบการเลือกคำตอบของ lead (รันจากรากโปรเจกต์: python tests/test_pick_answer.py)"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # หา gateway ใน src/
os.environ["AION_SESSION_FILE"] = os.path.join(tempfile.mkdtemp(), "s.json")
import gateway  # noqa: E402


def item(text):
    return {"content": {"content": text}}


# เหตุการณ์จริง: คำตอบสรุปยาว ตามด้วยข้อความขยะหลัง idle notification
items = [item("I'll ask each teammate."), item("S" * 1822), item("x" * 938), item("y" * 426), item("z" * 293)]

gateway.AION_ANSWER_MODE = "longest"
assert gateway.pick_answer(items) == "S" * 1822
gateway.AION_ANSWER_MODE = "last"
assert gateway.pick_answer(items) == "z" * 293
gateway.AION_ANSWER_MODE = "all"
assert gateway.pick_answer(items).startswith("I'll") and gateway.pick_answer(items).endswith("z" * 293)
assert gateway.pick_answer([item("  "), item("")]) == ""
print("ผ่านทั้งหมด")


# ---- โหมด smart: ใช้ลำดับเหตุการณ์ ----
def ev(kind, text="", teammate=False):
    c = {"content": text}
    if teammate:
        c["teammate_message"] = True
    return {"type": kind, "position": "left", "status": "finish", "content": c}


gateway.AION_ANSWER_MODE = "smart"
# 1) เหตุการณ์จริง: สรุปหลังเรียกเครื่องมืออ่านข้อความ แล้วโดนปลุกซ้ำ 3 ครั้ง
after = [ev("text", "ask", ), ev("tool_call"), ev("text", "mm", teammate=True), ev("tool_call"),
         ev("text", "S" * 300), ev("text", "d", teammate=True), ev("text", "n" * 200), ev("text", "n" * 100)]
assert gateway._smart_answer(after) == "S" * 300

# 2) lead สรุปคำตอบจริงทันทีหลังสมาชิกรายงาน (ไม่มี tool call คั่น) และยาวกว่าข้อความปกติ -> ต้องได้คำตอบนั้น
after = [ev("text", "plan " * 10), ev("tool_call"), ev("text", "report", teammate=True), ev("text", "A" * 500)]
assert gateway._smart_answer(after) == "A" * 500

# 3) ไม่มีข้อความปกติเลย -> ใช้ข้อความสุดท้าย
after = [ev("text", "r", teammate=True), ev("text", "only answer")]
assert gateway._smart_answer(after) == "only answer"

# 4) ผ่าน pick_answer
assert gateway.pick_answer([ev("text", "x")], [ev("tool_call"), ev("text", "final")]) == "final"
print("ผ่าน smart")
