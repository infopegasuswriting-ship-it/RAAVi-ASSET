"""RAAVi standalone HTTP server (presentation transport over independent core modules)."""
from __future__ import annotations

import json
import os
import re
import socket
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import raavi_auth
import raavi_engine
from raavi_bank import CHAPTERS, CHAT_PRACTICE_DIR, MAP_ASSETS
from raavi_db import DEFAULT_DB, connect_db, init_db

ROOT = Path(__file__).resolve().parent
PORT = int(os.getenv("RAAVI_PORT", "8766"))
HOST = os.getenv("RAAVI_HOST", "127.0.0.1")

STATIC_FILES: dict[str, tuple[Path, str]] = {
    "/": (ROOT / "index.html", "text/html; charset=utf-8"),
    "/index.html": (ROOT / "index.html", "text/html; charset=utf-8"),
    "/app.js": (ROOT / "app.js", "application/javascript; charset=utf-8"),
    "/style.css": (ROOT / "style.css", "text/css; charset=utf-8"),
    "/city-pins.png": (CHAT_PRACTICE_DIR / "city-pins.png", "image/png"),
    "/barrage-pins.png": (CHAT_PRACTICE_DIR / "barrage-pins.png", "image/png"),
    "/assets/city-pins.png": (CHAT_PRACTICE_DIR / "city-pins.png", "image/png"),
    "/assets/barrage-pins.png": (CHAT_PRACTICE_DIR / "barrage-pins.png", "image/png"),
}


class RaaviHandler(BaseHTTPRequestHandler):
    server_version = "RAAVi/2.0"
    db_path = DEFAULT_DB

    def log_message(self, format: str, *args) -> None:
        # Clean concise logging
        print(f"[{self.log_date_time_string()}] {format % args}", flush=True)

    def _send_json(self, status: int, payload: dict | list, cookie: str | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str, code: str = "error") -> None:
        self._send_json(status, {"error": message, "code": code})

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 262_144:
            raise ValueError("Request body too large.")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object.")
        return data

    def _get_session_token(self) -> str | None:
        raw_cookie = self.headers.get("Cookie", "")
        if not raw_cookie:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(raw_cookie)
        except Exception:
            return None
        morsel = cookie.get("raavi_sid")
        return morsel.value if morsel else None

    def _base_url(self) -> str:
        host = self.headers.get("Host") or f"{HOST}:{PORT}"
        proto = "https" if os.getenv("RAAVI_HTTPS", "").strip() in ("1", "true") else "http"
        return f"{proto}://{host}"

    def _require_verified_student(self, db, now: float):
        student = raavi_auth.get_student_from_token(db, self._get_session_token(), now)
        if not student:
            raise raavi_auth.AuthError("Please sign in to continue.", status=401)
        if student["verified_at"] is None:
            raise raavi_auth.AuthError("Please verify your email address before starting or resuming a test.", status=403)
        return student

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in STATIC_FILES:
            file_path, ctype = STATIC_FILES[path]
            if not file_path.is_file():
                self._send_error(404, f"Missing asset: {file_path.name}", code="missing_asset")
                return
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache" if ctype.startswith("text/") or ctype.startswith("application/") else "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
            return

        now = time.time()
        db = connect_db(self.db_path)
        try:
            if path == "/api/health":
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "env": "production" if raavi_auth.is_production() else "development",
                        "smtp_configured": raavi_auth.smtp_configured(),
                        "server_now": now,
                    },
                )
                return

            if path == "/api/me":
                student = raavi_auth.get_student_from_token(db, self._get_session_token(), now)
                user = (
                    {
                        "id": student["id"],
                        "email": student["email"],
                        "verified": student["verified_at"] is not None,
                    }
                    if student
                    else None
                )
                self._send_json(
                    200,
                    {
                        "user": user,
                        "smtp_configured": raavi_auth.smtp_configured(),
                        "dev_mail_preview": raavi_auth.allow_dev_mail_preview(),
                        "server_now": now,
                    },
                )
                return

            if path == "/api/subjects":
                student = raavi_auth.get_student_from_token(db, self._get_session_token(), now)
                if student and student["verified_at"] is not None:
                    subjects = {
                        subj: raavi_engine.subject_availability(db, student["id"], subj, now)
                        for subj in ("History", "Geography")
                    }
                else:
                    subjects = {
                        subj: {
                            "subject": subj,
                            "available": True,
                            "cooldown_seconds": 0,
                            "next_available_at": None,
                            "server_now": now,
                            "unfinished_blocking_new": False,
                            "active_session": None,
                        }
                        for subj in ("History", "Geography")
                    }
                self._send_json(200, {"subjects": subjects, "server_now": now, "chapter_counts": {s: len(CHAPTERS[s]) for s in CHAPTERS}})
                return

            m_ch = re.fullmatch(r"/api/chapters/([^/]+)", path)
            if m_ch:
                subj = unquote(m_ch.group(1))
                if subj not in CHAPTERS:
                    self._send_error(404, "Subject not found.")
                    return
                student = raavi_auth.get_student_from_token(db, self._get_session_token(), now)
                if student and student["verified_at"] is not None:
                    chapters = raavi_engine.get_chapter_summaries(db, student["id"], subj)
                    avail = raavi_engine.subject_availability(db, student["id"], subj, now)
                else:
                    chapters = [
                        {
                            "number": idx,
                            "subject": subj,
                            "chapter": ch,
                            "bank_count": db.execute(
                                "SELECT count(*) FROM questions WHERE subject=? AND chapter=? AND auto_status='passed'",
                                (subj, ch),
                            ).fetchone()[0],
                            "completed_attempts": 0,
                            "latest_report_id": None,
                            "latest_score": None,
                            "latest_total": 10,
                            "latest_completed_at": None,
                            "previous_score": None,
                            "active_session": None,
                        }
                        for idx, ch in enumerate(CHAPTERS[subj], 1)
                    ]
                    avail = {
                        "subject": subj,
                        "available": True,
                        "cooldown_seconds": 0,
                        "next_available_at": None,
                        "server_now": now,
                        "unfinished_blocking_new": False,
                        "active_session": None,
                    }
                self._send_json(200, {"subject": subj, "availability": avail, "chapters": chapters, "server_now": now})
                return

            m_test = re.fullmatch(r"/api/test/(\d+)", path)
            if m_test:
                student = self._require_verified_student(db, now)
                session_id = int(m_test.group(1))
                payload = raavi_engine.get_test_state(db, student["id"], session_id, now)
                self._send_json(200, payload)
                return

            if path == "/api/reports":
                student = self._require_verified_student(db, now)
                reports = raavi_engine.list_reports(db, student["id"])
                self._send_json(200, {"reports": reports})
                return

            m_rep = re.fullmatch(r"/api/reports/(\d+)", path)
            if m_rep:
                student = self._require_verified_student(db, now)
                rid = int(m_rep.group(1))
                report = raavi_engine.get_report(db, student["id"], rid)
                self._send_json(200, {"report": report})
                return

            if path == "/api/inventory":
                audit = db.execute("SELECT summary_json FROM import_audits ORDER BY id DESC LIMIT 1").fetchone()
                if not audit:
                    self._send_json(200, {"chapters": [], "total_imported": 0})
                    return
                summary = json.loads(audit["summary_json"])
                # Strip verbose issue list if huge, keep chapter inventory and counts
                self._send_json(
                    200,
                    {
                        "total_imported": summary["total_imported"],
                        "auto_passed": summary["auto_passed"],
                        "auto_flagged": summary["auto_flagged"],
                        "by_subject": summary["by_subject"],
                        "chapters": summary["chapters"],
                        "map_assets": {k: (CHAT_PRACTICE_DIR / k).is_file() for k in MAP_ASSETS},
                    },
                )
                return

            self._send_error(404, "Endpoint not found.")
        except raavi_auth.AuthError as exc:
            self._send_error(exc.status, str(exc), code="auth_error")
        except raavi_engine.EngineError as exc:
            self._send_error(exc.status, str(exc), code=exc.code)
        except Exception as exc:
            self._send_error(500, f"Unexpected server error: {exc}")
        finally:
            db.close()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        now = time.time()
        db = connect_db(self.db_path)
        try:
            data = self._read_json()

            if path == "/api/auth/register":
                db.execute("BEGIN IMMEDIATE")
                res = raavi_auth.register_student(
                    db, data.get("email"), data.get("password"), now, base_url=self._base_url()
                )
                db.commit()
                cookie = res.pop("cookie")
                self._send_json(201, res, cookie=cookie)
                return

            if path == "/api/auth/login":
                db.execute("BEGIN IMMEDIATE")
                res = raavi_auth.login_student(db, data.get("email"), data.get("password"), now)
                db.commit()
                cookie = res.pop("cookie")
                self._send_json(200, res, cookie=cookie)
                return

            if path == "/api/auth/verify":
                db.execute("BEGIN IMMEDIATE")
                res = raavi_auth.verify_email(
                    db,
                    data.get("email"),
                    code_raw=data.get("code"),
                    token_raw=data.get("token"),
                    now=now,
                )
                db.commit()
                cookie = res.pop("cookie")
                self._send_json(200, res, cookie=cookie)
                return

            if path == "/api/auth/resend":
                db.execute("BEGIN IMMEDIATE")
                res = raavi_auth.resend_verification(db, data.get("email"), now, base_url=self._base_url())
                db.commit()
                self._send_json(200, res)
                return

            if path == "/api/auth/forgot-password":
                db.execute("BEGIN IMMEDIATE")
                res = raavi_auth.request_password_reset(db, data.get("email"), now)
                db.commit()
                self._send_json(200, res)
                return

            if path == "/api/auth/reset-password":
                db.execute("BEGIN IMMEDIATE")
                res = raavi_auth.reset_password(
                    db, data.get("email"), data.get("code"), data.get("password"), now
                )
                db.commit()
                cookie = res.pop("cookie")
                self._send_json(200, res, cookie=cookie)
                return

            if path == "/api/auth/logout":
                db.execute("BEGIN IMMEDIATE")
                cookie = raavi_auth.logout_student(db, self._get_session_token())
                db.commit()
                self._send_json(200, {"ok": True}, cookie=cookie)
                return

            if path == "/api/start-test":
                student = self._require_verified_student(db, now)
                res = raavi_engine.start_chapter_test(
                    db,
                    student["id"],
                    str(data.get("subject", "")),
                    str(data.get("chapter", "")),
                    str(data.get("nonce", "")),
                    now,
                )
                self._send_json(200, res)
                return

            m_ans = re.fullmatch(r"/api/test/(\d+)/answer", path)
            if m_ans:
                student = self._require_verified_student(db, now)
                session_id = int(m_ans.group(1))
                res = raavi_engine.submit_answer(
                    db,
                    student["id"],
                    session_id,
                    data.get("question_index"),
                    data.get("response"),
                    bool(data.get("skip", False)),
                    now,
                )
                self._send_json(200, res)
                return

            m_end = re.fullmatch(r"/api/test/(\d+)/end-incomplete", path)
            if m_end:
                student = self._require_verified_student(db, now)
                session_id = int(m_end.group(1))
                report = raavi_engine.end_unfinished_test(db, student["id"], session_id, now)
                self._send_json(200, {"report": report})
                return

            self._send_error(404, "Endpoint not found.")
        except raavi_auth.AuthError as exc:
            db.rollback()
            self._send_error(exc.status, str(exc), code="auth_error")
        except raavi_engine.EngineError as exc:
            db.rollback()
            self._send_error(exc.status, str(exc), code=exc.code)
        except (ValueError, json.JSONDecodeError) as exc:
            db.rollback()
            self._send_error(400, str(exc))
        except Exception as exc:
            db.rollback()
            self._send_error(500, f"Unexpected server error: {exc}")
        finally:
            db.close()


class RaaviHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def create_server(host: str = HOST, port: int = PORT, db_path: str | Path = DEFAULT_DB) -> ThreadingHTTPServer:
    init_db(db_path, sync_bank=True)

    class BoundHandler(RaaviHandler):
        pass

    BoundHandler.db_path = Path(db_path)
    return RaaviHTTPServer((host, port), BoundHandler)


if __name__ == "__main__":
    srv = create_server(HOST, PORT, DEFAULT_DB)
    print(f"RAAVi available at http://{HOST}:{PORT}", flush=True)
    srv.serve_forever()
