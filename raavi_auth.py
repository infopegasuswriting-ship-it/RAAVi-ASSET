"""RAAVi authentication, email verification, password reset, and session management."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import smtplib
import sqlite3
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CODE_TTL_SECONDS = 900  # 15 minutes
MAX_CODE_TRIES = 5
RESEND_COOLDOWN_SECONDS = 30
SESSION_TTL_SECONDS = 30 * 86400
PBKDF2_ITERATIONS = 200_000

ROOT = Path(__file__).resolve().parent
DEV_MAIL_LOG = Path(os.getenv("RAAVI_DEV_MAIL_LOG", str(ROOT / "dev-emails.log")))


class AuthError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def is_production() -> bool:
    return os.getenv("RAAVI_ENV", "development").strip().lower() == "production"


def smtp_configured() -> bool:
    return bool(os.getenv("RAAVI_SMTP_HOST", "").strip() and os.getenv("RAAVI_SMTP_FROM", "").strip())


def allow_dev_mail_preview() -> bool:
    if is_production():
        return False
    override = os.getenv("RAAVI_DEV_MAIL_PREVIEW", "").strip().lower()
    if override in ("0", "false", "no"):
        return False
    return not smtp_configured()


def token_digest(token: str) -> str:
    secret = os.getenv("RAAVI_SECRET", "")
    if secret:
        return hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters long.")
    if salt is None:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iters_str, salt_hex, dk_hex = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iters = int(iters_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(dk_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def normalize_email(raw: Any) -> str:
    email = str(raw or "").strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise AuthError("Enter a valid email address.")
    return email


def send_email_message(recipient: str, subject: str, body: str, code: str) -> dict[str, Any]:
    """
    Send an email via SMTP when configured, or record it to the local development
    outbox when running in development mode without SMTP.
    """
    if smtp_configured():
        host = os.environ["RAAVI_SMTP_HOST"].strip()
        port = int(os.getenv("RAAVI_SMTP_PORT", "465"))
        sender = os.environ["RAAVI_SMTP_FROM"].strip()
        user = os.getenv("RAAVI_SMTP_USER", "").strip()
        password = os.getenv("RAAVI_SMTP_PASS", os.getenv("RAAVI_SMTP_PASSWORD", ""))
        use_starttls = os.getenv("RAAVI_SMTP_STARTTLS", "").strip().lower() in ("1", "true", "yes") or port == 587

        msg = EmailMessage()
        msg["To"] = recipient
        msg["From"] = sender
        msg["Subject"] = subject
        msg.set_content(body)

        try:
            if use_starttls:
                with smtplib.SMTP(host, port, timeout=15) as smtp:
                    smtp.starttls()
                    if user:
                        smtp.login(user, password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
                    if user:
                        smtp.login(user, password)
                    smtp.send_message(msg)
        except OSError as exc:
            raise AuthError(
                "Email delivery is currently unavailable. Please try again in a moment.",
                status=503,
            ) from exc
        return {"delivery": "smtp"}

    if is_production():
        raise AuthError(
            "Email service is not configured for production. Contact the site administrator.",
            status=503,
        )

    # Local development email delivery: stdout + dev-emails.log
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{stamp}] TO: {recipient} | SUBJECT: {subject}\n{body}\n{'-' * 60}\n"
    try:
        with DEV_MAIL_LOG.open("a", encoding="utf-8") as fh:
            fh.write(entry)
    except OSError:
        pass
    print(f"[RAAVi DEV MAIL] {recipient} | {subject} | Code: {code}", flush=True)
    result: dict[str, Any] = {"delivery": "dev_log"}
    if allow_dev_mail_preview():
        result["dev_code"] = code
    return result


def _issue_code(
    db: sqlite3.Connection,
    email: str,
    purpose: str,
    now: float,
    base_url: str = "",
) -> dict[str, Any]:
    existing = db.execute(
        "SELECT issued_at FROM auth_codes WHERE email=? AND purpose=?",
        (email, purpose),
    ).fetchone()
    if existing and (now - existing["issued_at"]) < RESEND_COOLDOWN_SECONDS:
        wait = int(RESEND_COOLDOWN_SECONDS - (now - existing["issued_at"])) + 1
        raise AuthError(f"Please wait {wait}s before requesting another code.", status=429)

    code = f"{secrets.randbelow(1_000_000):06d}"
    link_token = secrets.token_urlsafe(24)
    db.execute(
        """
        INSERT OR REPLACE INTO auth_codes (email, purpose, code_hash, token_hash, issued_at, tries)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (email, purpose, token_digest(code), token_digest(link_token), now),
    )

    if purpose == "verify":
        subject = "Verify your RAAVi student account"
        verify_link = f"{base_url.rstrip('/')}/?verify_token={link_token}&email={email}" if base_url else ""
        body = (
            f"Welcome to RAAVi — Your Personal Examiner for Pakistan Studies.\n\n"
            f"Your 6-digit verification code is: {code}\n"
            f"This code expires in 15 minutes.\n"
        )
        if verify_link:
            body += f"\nOr open this verification link:\n{verify_link}\n"
    else:
        subject = "Reset your RAAVi password"
        body = (
            f"A password reset was requested for your RAAVi student account.\n\n"
            f"Your 6-digit password reset code is: {code}\n"
            f"This code expires in 15 minutes. If you did not request this, ignore this email.\n"
        )

    delivery_info = send_email_message(email, subject, body, code)
    if allow_dev_mail_preview() and purpose == "verify":
        delivery_info["dev_link_token"] = link_token
    return delivery_info


def create_session(db: sqlite3.Connection, student_id: int, now: float) -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    expires = now + SESSION_TTL_SECONDS
    db.execute(
        "INSERT INTO student_sessions (token_hash, student_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (token_digest(raw_token), student_id, expires, now),
    )
    cookie_parts = [
        f"raavi_sid={raw_token}",
        "HttpOnly",
        "SameSite=Lax",
        "Path=/",
        f"Max-Age={SESSION_TTL_SECONDS}",
    ]
    if is_production() and os.getenv("RAAVI_HTTPS", "").strip() in ("1", "true"):
        cookie_parts.append("Secure")
    return raw_token, "; ".join(cookie_parts)


def get_student_from_token(db: sqlite3.Connection, raw_token: str | None, now: float) -> sqlite3.Row | None:
    if not raw_token:
        return None
    row = db.execute(
        """
        SELECT s.id, s.email, s.verified_at, s.created_at
        FROM student_sessions ss
        JOIN students s ON s.id = ss.student_id
        WHERE ss.token_hash = ? AND ss.expires_at > ?
        """,
        (token_digest(raw_token), now),
    ).fetchone()
    return row


def register_student(
    db: sqlite3.Connection,
    email_raw: Any,
    password_raw: Any,
    now: float,
    base_url: str = "",
) -> dict[str, Any]:
    email = normalize_email(email_raw)
    password = str(password_raw or "")
    pw_hash = hash_password(password)

    existing = db.execute("SELECT id, verified_at FROM students WHERE email=?", (email,)).fetchone()
    if existing:
        if existing["verified_at"] is not None:
            raise AuthError("An account with this email already exists. Please sign in instead.", status=409)
        # Re-registering an unverified account updates password and resends code
        db.execute("UPDATE students SET password_hash=? WHERE id=?", (pw_hash, existing["id"]))
        student_id = existing["id"]
    else:
        student_id = db.execute(
            "INSERT INTO students (email, password_hash, verified_at, created_at) VALUES (?, ?, NULL, ?)",
            (email, pw_hash, now),
        ).lastrowid

    mail_meta = _issue_code(db, email, "verify", now, base_url=base_url)
    _, cookie = create_session(db, student_id, now)
    return {
        "user": {"id": student_id, "email": email, "verified": False},
        "cookie": cookie,
        **mail_meta,
    }


def login_student(db: sqlite3.Connection, email_raw: Any, password_raw: Any, now: float) -> dict[str, Any]:
    email = normalize_email(email_raw)
    password = str(password_raw or "")
    row = db.execute("SELECT * FROM students WHERE email=?", (email,)).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        raise AuthError("Incorrect email or password.", status=401)
    _, cookie = create_session(db, row["id"], now)
    return {
        "user": {"id": row["id"], "email": row["email"], "verified": row["verified_at"] is not None},
        "cookie": cookie,
    }


def resend_verification(
    db: sqlite3.Connection,
    email_raw: Any,
    now: float,
    base_url: str = "",
) -> dict[str, Any]:
    email = normalize_email(email_raw)
    row = db.execute("SELECT id, verified_at FROM students WHERE email=?", (email,)).fetchone()
    if not row:
        raise AuthError("No account found for that email address.", status=404)
    if row["verified_at"] is not None:
        raise AuthError("This email address is already verified. Please sign in.", status=400)
    mail_meta = _issue_code(db, email, "verify", now, base_url=base_url)
    return {"ok": True, **mail_meta}


def verify_email(
    db: sqlite3.Connection,
    email_raw: Any,
    code_raw: Any = None,
    token_raw: Any = None,
    now: float = 0.0,
) -> dict[str, Any]:
    email = normalize_email(email_raw)
    entry = db.execute(
        "SELECT * FROM auth_codes WHERE email=? AND purpose='verify'",
        (email,),
    ).fetchone()
    if not entry or (now - entry["issued_at"]) >= CODE_TTL_SECONDS or entry["tries"] >= MAX_CODE_TRIES:
        raise AuthError("Verification code expired or locked. Request a new code.", status=400)

    db.execute(
        "UPDATE auth_codes SET tries = tries + 1 WHERE email=? AND purpose='verify'",
        (email,),
    )

    matched = False
    if token_raw:
        matched = hmac.compare_digest(entry["token_hash"], token_digest(str(token_raw).strip()))
    elif code_raw is not None:
        code = str(code_raw).strip()
        if len(code) == 6 and code.isdigit():
            matched = hmac.compare_digest(entry["code_hash"], token_digest(code))

    if not matched:
        db.commit()
        raise AuthError("Incorrect verification code.", status=400)

    db.execute("DELETE FROM auth_codes WHERE email=? AND purpose='verify'", (email,))
    db.execute(
        "UPDATE students SET verified_at = COALESCE(verified_at, ?) WHERE email=?",
        (now, email),
    )
    row = db.execute("SELECT id, email, verified_at FROM students WHERE email=?", (email,)).fetchone()
    if not row:
        raise AuthError("Account not found.", status=404)
    _, cookie = create_session(db, row["id"], now)
    return {
        "user": {"id": row["id"], "email": row["email"], "verified": True},
        "cookie": cookie,
    }


def request_password_reset(db: sqlite3.Connection, email_raw: Any, now: float) -> dict[str, Any]:
    email = normalize_email(email_raw)
    row = db.execute("SELECT id FROM students WHERE email=?", (email,)).fetchone()
    if not row:
        # Generic response to avoid account enumeration in production
        return {"ok": True, "message": "If an account exists for that email, a reset code has been sent."}
    mail_meta = _issue_code(db, email, "reset", now)
    return {
        "ok": True,
        "message": "If an account exists for that email, a reset code has been sent.",
        **mail_meta,
    }


def reset_password(
    db: sqlite3.Connection,
    email_raw: Any,
    code_raw: Any,
    new_password_raw: Any,
    now: float,
) -> dict[str, Any]:
    email = normalize_email(email_raw)
    code = str(code_raw or "").strip()
    new_hash = hash_password(str(new_password_raw or ""))

    entry = db.execute(
        "SELECT * FROM auth_codes WHERE email=? AND purpose='reset'",
        (email,),
    ).fetchone()
    if not entry or (now - entry["issued_at"]) >= CODE_TTL_SECONDS or entry["tries"] >= MAX_CODE_TRIES:
        raise AuthError("Reset code expired or locked. Request a new reset code.", status=400)

    db.execute(
        "UPDATE auth_codes SET tries = tries + 1 WHERE email=? AND purpose='reset'",
        (email,),
    )
    if not (len(code) == 6 and code.isdigit() and hmac.compare_digest(entry["code_hash"], token_digest(code))):
        db.commit()
        raise AuthError("Incorrect reset code.", status=400)

    row = db.execute("SELECT id FROM students WHERE email=?", (email,)).fetchone()
    if not row:
        raise AuthError("Account not found.", status=404)

    db.execute("DELETE FROM auth_codes WHERE email=? AND purpose='reset'", (email,))
    # Resetting password via email ownership also confirms email ownership if not yet verified
    db.execute(
        "UPDATE students SET password_hash=?, verified_at=COALESCE(verified_at, ?) WHERE id=?",
        (new_hash, now, row["id"]),
    )
    # Invalidate existing sessions on password reset
    db.execute("DELETE FROM student_sessions WHERE student_id=?", (row["id"],))
    _, cookie = create_session(db, row["id"], now)
    return {
        "user": {"id": row["id"], "email": email, "verified": True},
        "cookie": cookie,
    }


def logout_student(db: sqlite3.Connection, raw_token: str | None) -> str:
    if raw_token:
        db.execute("DELETE FROM student_sessions WHERE token_hash=?", (token_digest(raw_token),))
    return "raavi_sid=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"
