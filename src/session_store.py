"""
session_store.py: ที่เก็บ session ของ AionUi (cookie + CSRF token) ที่ต่ออายุได้โดยไม่ต้องรีสตาร์ท

หลักการ
- ค่าเก็บในไฟล์ session_state.json ที่รากโปรเจกต์ (เปลี่ยนที่อยู่ได้ด้วย AION_SESSION_FILE)
- ทุกครั้งที่สร้างคำขอ จะเช็กเวลาแก้ไขไฟล์ ถ้ามีค่าใหม่ (จาก scripts/update_session.py) จะโหลดใหม่ทันที
- ถ้า AionUi ส่ง Set-Cookie กลับมา (ต่ออายุ session) จะอัปเดตค่าและบันทึกลงไฟล์ให้เอง
- ค่าเริ่มต้นอ่านจาก AION_SESSION_COOKIE / AION_CSRF_TOKEN ครั้งแรกที่ยังไม่มีไฟล์
  (ถ้าเริ่มโปรแกรมด้วยค่า env ที่ต่างจากครั้งก่อน จะถือว่าผู้ใช้ตั้งใจเปลี่ยน และใช้ค่า env แทนไฟล์)

คำเตือน: ไฟล์นี้เทียบเท่ารหัสผ่านของ AionUi ห้าม commit ขึ้น Git (ใส่ session_state.json ใน .gitignore)
"""

import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie

# ค่าตั้งต้น: session_state.json ที่รากโปรเจกต์ (ไม่ขึ้นกับว่ารันจากโฟลเดอร์ไหน) เปลี่ยนได้ด้วย AION_SESSION_FILE
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSION_FILE = os.environ.get("AION_SESSION_FILE", os.path.join(_PROJECT_ROOT, "session_state.json"))
# ถ้า CSRF token ถูกเก็บเป็น cookie (แบบ double-submit) ให้ตั้งชื่อ cookie นั้น จะใช้ค่านั้นเป็น header ให้อัตโนมัติ
CSRF_COOKIE_NAME = os.environ.get("AION_CSRF_COOKIE_NAME", "aionui-csrf-token")
# cookie ต่ออายุ: HttpOnly และจำกัด Path ไว้ที่ /api/auth/refresh (เบราว์เซอร์ส่งให้เฉพาะ path นี้)
REFRESH_COOKIE_NAME = "aionui-refresh"
REFRESH_PATH = "/api/auth/refresh"
# cookie วิเคราะห์ (analytics) ไม่จำเป็นต่อการเรียก API ไม่เก็บ เพื่อให้ไฟล์ลับเล็กลง
_SKIP_PREFIXES = ("rl_", "ph_")


def _keep(name: str) -> bool:
    return not name.startswith(_SKIP_PREFIXES)


class FileLock:
    """lock ข้ามโปรเซสแบบง่าย (สร้างไฟล์ด้วย O_EXCL) กัน gateway กับ MCP server refresh พร้อมกัน"""

    def __init__(self, path: str, timeout: float = 20.0, stale: float = 60.0):
        self.path, self.timeout, self.stale = path, timeout, stale

    def acquire(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > self.stale:
                        os.remove(self.path)  # lock ค้างจากโปรเซสที่ตาย
                        continue
                except OSError:
                    pass
                if time.time() > deadline:
                    raise TimeoutError("รอ lock ของ session ไม่ได้")
                time.sleep(0.1)

    def release(self):
        try:
            os.remove(self.path)
        except OSError:
            pass


def parse_cookie_header(s: str) -> dict:
    out = {}
    for part in (s or "").split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        if k.strip() and _keep(k.strip()):
            out[k.strip()] = v.strip()
    return out


def build_cookie_header(cookies: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def jwt_exp(value: str):
    """ถ้า value เป็น JWT ที่มีฟิลด์ exp คืนเวลาหมดอายุ (epoch วินาที) ไม่งั้นคืน None (ไม่ตรวจลายเซ็น แค่อ่านวันหมดอายุ)"""
    parts = (value or "").split(".")
    if len(parts) != 3:
        return None
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        exp = data.get("exp")
        return float(exp) if isinstance(exp, (int, float)) else None
    except Exception:
        return None


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


class SessionStore:
    def __init__(self, path: str = None):
        self.path = path or SESSION_FILE
        self.cookies: dict = {}
        self.csrf: str = ""
        self.meta: dict = {}          # name -> {"expires_at": epoch} จาก Set-Cookie
        self._env_hash = ""
        self._mtime = None
        self.last_refresh_at = None   # epoch ของการ refresh สำเร็จครั้งล่าสุด
        self._load_initial()

    # ---------- โหลด / บันทึก ----------
    def _load_initial(self):
        env_cookie = os.environ.get("AION_SESSION_COOKIE", "").strip()
        env_csrf = os.environ.get("AION_CSRF_TOKEN", "").strip()
        env_hash = (
            hashlib.sha256((env_cookie + "\n" + env_csrf).encode()).hexdigest()
            if (env_cookie or env_csrf)
            else ""
        )
        data = self._read_file()
        if data:
            self._apply(data)
            if env_hash and data.get("env_hash") != env_hash:
                # ผู้ใช้เริ่มโปรแกรมด้วยค่า env ชุดใหม่ ให้ใช้ค่านั้นแทนไฟล์
                if env_cookie:
                    self.cookies = parse_cookie_header(env_cookie)
                    self.meta = {}
                if env_csrf:
                    self.csrf = env_csrf
                self._env_hash = env_hash
                self.save()
        else:
            self.cookies = parse_cookie_header(env_cookie)
            self.csrf = env_csrf
            self._env_hash = env_hash
            if self.cookies or self.csrf:
                self.save()

    def _read_file(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self._mtime = os.path.getmtime(self.path)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def _apply(self, data: dict):
        self.cookies = dict(data.get("cookies") or {})
        self.csrf = data.get("csrf") or ""
        self.meta = dict(data.get("meta") or {})
        self._env_hash = data.get("env_hash") or ""
        self.last_refresh_at = data.get("last_refresh_at")

    def refresh_from_disk(self):
        """ถ้าไฟล์ถูกแก้ (เช่นรัน update_session.py) ให้โหลดค่าใหม่ ไม่ต้องรีสตาร์ท"""
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return
        if mtime != self._mtime:
            data = self._read_file()
            if data:
                self._apply(data)

    def save(self):
        data = {
            "cookies": self.cookies,
            "csrf": self.csrf,
            "meta": self.meta,
            "env_hash": self._env_hash,
            "last_refresh_at": self.last_refresh_at,
            "updated_at": _iso(time.time()),
        }
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        try:
            self._mtime = os.path.getmtime(self.path)
        except OSError:
            pass

    # ---------- ค่าที่ใช้ตอนเรียก ----------
    def _cookie_path(self, name: str) -> str:
        p = self.meta.get(name, {}).get("path")
        return p or (REFRESH_PATH if name == REFRESH_COOKIE_NAME else "/")

    def cookie_header(self, path: str = "/") -> str:
        """Cookie ที่เบราว์เซอร์จะส่งไปยัง path นี้ (aionui-refresh ส่งเฉพาะ /api/auth/refresh)"""
        self.refresh_from_disk()
        return build_cookie_header(
            {k: v for k, v in self.cookies.items() if path.startswith(self._cookie_path(k))}
        )

    def has_refresh_token(self) -> bool:
        self.refresh_from_disk()
        return bool(self.cookies.get(REFRESH_COOKIE_NAME))

    def fingerprint(self) -> str:
        """ลายนิ้วมือของ session ปัจจุบัน ใช้ดูว่ามีใครต่ออายุไปแล้วหรือยัง (ไม่เปิดเผยค่า)"""
        self.refresh_from_disk()
        raw = "|".join(self.cookies.get(n, "") for n in ("aionui-session", REFRESH_COOKIE_NAME))
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def refresh_lock(self) -> FileLock:
        return FileLock(self.path + ".lock")

    def apply_tokens(self, token: str = None, refresh_token: str = None) -> bool:
        """รับโทเค็นจาก body ของ /api/auth/refresh (token = JWT ของ session, refresh_token = ตัวต่ออายุ)"""
        changed = False
        for name, val in (("aionui-session", token), (REFRESH_COOKIE_NAME, refresh_token)):
            if val and self.cookies.get(name) != val:
                self.cookies[name] = val
                changed = True
                if name == REFRESH_COOKIE_NAME:
                    self.meta[name] = {**self.meta.get(name, {}), "path": REFRESH_PATH}
        if changed:
            self.save()
        return changed

    def mark_refreshed(self):
        self.last_refresh_at = time.time()
        self.save()

    def csrf_token(self) -> str:
        self.refresh_from_disk()
        if CSRF_COOKIE_NAME and CSRF_COOKIE_NAME in self.cookies:
            return self.cookies[CSRF_COOKIE_NAME]
        return self.csrf

    def has_session(self) -> bool:
        self.refresh_from_disk()
        return bool(self.cookies)

    def set_credentials(self, cookie_header: str = None, csrf: str = None, refresh: str = None):
        """ตั้งค่าใหม่ (ใช้จาก update_session.py) cookie ที่วางมาใหม่จะแทนของเดิมทั้งชุด
        refresh = ค่า cookie aionui-refresh (HttpOnly จึงไม่อยู่ในบรรทัด Cookie ของ Network tab)"""
        self.refresh_from_disk()
        if cookie_header:
            self.cookies = parse_cookie_header(cookie_header)
            self.meta = {}
        if refresh:
            self.cookies[REFRESH_COOKIE_NAME] = refresh.strip()
            self.meta[REFRESH_COOKIE_NAME] = {
                **self.meta.get(REFRESH_COOKIE_NAME, {}), "path": REFRESH_PATH}
        if csrf:
            self.csrf = csrf
        self.save()

    # ---------- อัปเดตจากคำตอบของ AionUi ----------
    def update_from_response(self, response) -> bool:
        """อ่าน Set-Cookie / x-csrf-token จากคำตอบของ AionUi (ถ้ามีการต่ออายุ) คืน True ถ้ามีการเปลี่ยนแปลง"""
        changed = False
        for raw in response.headers.get_list("set-cookie"):
            sc = SimpleCookie()
            try:
                sc.load(raw)
            except Exception:
                continue
            for name, m in sc.items():
                if not _keep(name):
                    continue
                if m["max-age"] == "0" or m.value == "":
                    if name in self.cookies:
                        del self.cookies[name]
                        self.meta.pop(name, None)
                        changed = True
                    continue
                if self.cookies.get(name) != m.value:
                    self.cookies[name] = m.value
                    changed = True
                new_meta = dict(self.meta.get(name, {}))
                exp = self._expiry_of(m)
                if exp:
                    new_meta["expires_at"] = exp
                if m["path"]:
                    new_meta["path"] = m["path"]
                if new_meta != self.meta.get(name, {}):
                    self.meta[name] = new_meta
                    changed = True
        tok = response.headers.get("x-csrf-token")
        if tok and tok != self.csrf:
            self.csrf = tok
            changed = True
        if changed:
            self.save()
        return changed

    @staticmethod
    def _expiry_of(morsel):
        try:
            if morsel["max-age"]:
                return time.time() + int(morsel["max-age"])
            if morsel["expires"]:
                return parsedate_to_datetime(morsel["expires"]).timestamp()
        except Exception:
            return None
        return None

    # ---------- ข้อมูลวันหมดอายุ (ไม่เปิดเผยค่า cookie) ----------
    def expiry_info(self) -> dict:
        self.refresh_from_disk()
        now = time.time()
        out = {}
        for name, value in self.cookies.items():
            exp = self.meta.get(name, {}).get("expires_at") or jwt_exp(value)
            if exp:
                out[name] = {"expires_at": _iso(exp), "seconds_left": int(exp - now)}
        return out


store = SessionStore()
