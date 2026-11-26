# RAAVi — Your Personal Examiner for PST

Standalone, mobile-friendly Pakistan Studies (Cambridge O Level 2059) practice application by **Khizar Hayat**.

## Student Journey
1. **Sign up or log in** with email verification, resend code, password reset, and persistent sessions (destination is preserved across email verification).
2. **Choose a subject** (**History** or **Geography**) with independent rolling 24-hour allowances and live countdown tickers.
3. **Browse chapters** (16 History chapters or 12 Geography chapters in KH notes order) showing latest score and completed attempts (`No attempts yet` for new chapters).
4. **Confirm and start** a 10-question test from the selected chapter (browsing never uses an allowance).
5. **Answer one question at a time** (`Submit answer` or `Skip`), with immediate KH-grounded feedback and progress saved after every response for seamless resumption across refreshes or devices.
6. **Review saved reports** with chapter score (`History · Uprising of 1857 · 7/10`), all 10 question outcomes (`✓ Correct`, `✗ Incorrect`, `— Skipped`), explanations, source page references, and comparable chapter progress trends.

## Local Quick Start (Windows)
1. Double-click `Start RAAVi.cmd` (or run `Start-RAAVi.ps1` in PowerShell), or run directly with Python 3.12+:
   ```powershell
   python server.py
   ```
2. Open `http://127.0.0.1:8766/` in your browser.
3. **Local email verification (development mode):** When `RAAVI_SMTP_HOST` is not set and `RAAVI_ENV` is not `production`, verification and password-reset codes are:
   - printed to the server console (`[RAAVi DEV MAIL] ... Code: 123456`),
   - appended to `dev-emails.log` in the project directory, and
   - displayed in an on-screen local development hint when `RAAVI_DEV_MAIL_PREVIEW=1`.

## Production Configuration
Copy `.env.example` to `.env` (or export environment variables in your host/process manager):

- `RAAVI_ENV=production` (disables local dev code preview and requires SMTP)
- `RAAVI_HOST=0.0.0.0` (or reverse-proxy loopback `127.0.0.1`)
- `RAAVI_PORT=8766`
- `RAAVI_HTTPS=1` (adds `Secure` flag to session cookies behind HTTPS)
- `RAAVI_DB=/path/to/raavi.sqlite3`
- `RAAVI_SECRET=<long-random-secret>` (used for HMAC hashing of session tokens and verification codes)
- `RAAVI_SMTP_HOST`, `RAAVI_SMTP_PORT` (`465` for SSL or `587` with `RAAVI_SMTP_STARTTLS=1`), `RAAVI_SMTP_USER`, `RAAVI_SMTP_PASS`, `RAAVI_SMTP_FROM`

## Architecture & Future Website Integration
Core assessment, bank management, and authentication logic are separated from the HTTP/SPA presentation layer:
- `raavi_bank.py` — Question bank importer, validation checks, immutable item versioning (`question_versions`), and chapter inventory.
- `raavi_engine.py` — 10-question chapter selector, 62-day family lockout, underlying fact-overlap prevention, max-2-matching rule, rolling 24h per-subject quota, deterministic grading, and comparable chapter reports.
- `raavi_auth.py` — PBKDF2 password hashing, email verification, password reset, and session tokens.
- `raavi_db.py` — SQLite schema and WAL connection helpers (keeps legacy pilot/demo tables `users`, `attempts`, `forms` separate from real `students` records).
- `server.py` — Thin HTTP JSON API + static file server (`index.html`, `app.js`, `style.css`, and `chat-practice/*.png`).

A larger website can either link to RAAVi's standalone deployment or import `raavi_auth`, `raavi_engine`, and `raavi_bank` directly behind unified routes/SSO.

## Validation & Capacity Reports
Run reproducible import validation and 184-day chapter capacity simulations anytime:
```powershell
python validate_and_simulate.py
```
This regenerates `validation-report.md` and `capacity-report.md`.
