"""End-to-end verification tests for RAAVi (Section 9 acceptance suite)."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import raavi_auth
import raavi_bank
import raavi_db
import raavi_engine
from server import create_server


class HttpClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.cj = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            return exc.code, json.loads(raw) if raw else {}

    def get_bytes(self, path: str) -> tuple[int, bytes, str]:
        req = urllib.request.Request(self.base_url + path, method="GET")
        with self.opener.open(req, timeout=15) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "")


class RaaviAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.tmpdir.name) / "test_raavi.sqlite3"
        # Copy legacy demo table into test DB to verify isolation
        con = sqlite3.connect(cls.db_path)
        con.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT UNIQUE, verified_at REAL)")
        con.execute("INSERT INTO users(email, verified_at) VALUES (NULL, NULL)")
        con.commit()
        con.close()

        os.environ["RAAVI_ENV"] = "development"
        os.environ["RAAVI_DEV_MAIL_LOG"] = str(Path(cls.tmpdir.name) / "dev-mail.log")
        cls.srv = create_server("127.0.0.1", 0, cls.db_path)
        cls.port = cls.srv.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmpdir.cleanup()

    def _register_and_verify(self, client: HttpClient, email: str, password: str = "StrongPass123"):
        status, reg = client.request("POST", "/api/auth/register", {"email": email, "password": password})
        self.assertEqual(status, 201, reg)
        self.assertFalse(reg["user"]["verified"])
        code = reg["dev_code"]

        # Unverified student cannot start a test
        st_block, block_data = client.request(
            "POST",
            "/api/start-test",
            {"subject": "History", "chapter": "Uprising of 1857", "nonce": "unverified-1"},
        )
        self.assertEqual(st_block, 403, block_data)

        # Resend code works after cooldown or verify directly
        st_v, vres = client.request("POST", "/api/auth/verify", {"email": email, "code": code})
        self.assertEqual(st_v, 200, vres)
        self.assertTrue(vres["user"]["verified"])
        return vres["user"]

    def test_01_auth_subjects_chapters_and_legacy_isolation(self):
        c = HttpClient(self.base_url)
        user = self._register_and_verify(c, "student1@example.com")

        # Verify legacy demo users table was not mixed with real students
        con = raavi_db.connect_db(self.db_path)
        try:
            demo_cnt = con.execute("SELECT count(*) FROM users WHERE email IS NULL").fetchone()[0]
            real_cnt = con.execute("SELECT count(*) FROM students WHERE id=?", (user["id"],)).fetchone()[0]
            self.assertEqual(demo_cnt, 1)
            self.assertEqual(real_cnt, 1)
        finally:
            con.close()

        # Subjects
        st, sdata = c.request("GET", "/api/subjects")
        self.assertEqual(st, 200)
        self.assertEqual(set(sdata["subjects"].keys()), {"History", "Geography"})

        # History = 16 chapters, Geography = 12 chapters
        st_h, hdata = c.request("GET", "/api/chapters/History")
        self.assertEqual(st_h, 200)
        self.assertEqual(len(hdata["chapters"]), 16)
        self.assertEqual(hdata["chapters"][0]["chapter"], "Mughal decline and British expansion")

        st_g, gdata = c.request("GET", "/api/chapters/Geography")
        self.assertEqual(st_g, 200)
        self.assertEqual(len(gdata["chapters"]), 12)
        self.assertEqual(gdata["chapters"][0]["chapter"], "Topography")

        # Password reset + logout + login flow
        st_out, _ = c.request("POST", "/api/auth/logout", {})
        self.assertEqual(st_out, 200)
        st_me, me_data = c.request("GET", "/api/me")
        self.assertIsNone(me_data["user"])

        st_fp, fp = c.request("POST", "/api/auth/forgot-password", {"email": "student1@example.com"})
        self.assertEqual(st_fp, 200)
        reset_code = fp["dev_code"]
        st_rp, rp = c.request(
            "POST",
            "/api/auth/reset-password",
            {"email": "student1@example.com", "code": reset_code, "password": "NewPassword456"},
        )
        self.assertEqual(st_rp, 200, rp)
        self.assertTrue(rp["user"]["verified"])

    def test_02_test_lifecycle_cooldown_idempotency_resume_grading_and_versions(self):
        c1 = HttpClient(self.base_url)
        user1 = self._register_and_verify(c1, "student2@example.com")

        # Start History test (double-click / same nonce idempotency)
        st1, res1 = c1.request(
            "POST",
            "/api/start-test",
            {"subject": "History", "chapter": "Uprising of 1857", "nonce": "nonce-abc"},
        )
        self.assertEqual(st1, 200, res1)
        st2, res2 = c1.request(
            "POST",
            "/api/start-test",
            {"subject": "History", "chapter": "Uprising of 1857", "nonce": "nonce-abc"},
        )
        self.assertEqual(st2, 200)
        self.assertEqual(res1["session_id"], res2["session_id"])
        self.assertTrue(res2["idempotent"])

        sid = res1["session_id"]

        # Another History chapter is immediately blocked by History active/cooldown
        st_other_h, err_h = c1.request(
            "POST",
            "/api/start-test",
            {"subject": "History", "chapter": "Sir Syed Ahmad Khan", "nonce": "nonce-def"},
        )
        self.assertIn(st_other_h, (409, 429))

        # Geography remains available!
        st_geo, res_geo = c1.request(
            "POST",
            "/api/start-test",
            {"subject": "Geography", "chapter": "Topography", "nonce": "nonce-geo-1"},
        )
        self.assertEqual(st_geo, 200, res_geo)

        # Fetch active History test -> verify no answer key leaked, 10 items, <= 2 matching
        st_t, tdata = c1.request("GET", f"/api/test/{sid}")
        self.assertEqual(st_t, 200)
        self.assertEqual(tdata["total"], 10)
        self.assertEqual(tdata["current_question"]["number"], 1)
        self.assertNotIn("answer_key", tdata["current_question"])
        self.assertNotIn("explanation", tdata["current_question"])
        first_choices = list(tdata["current_question"]["choices"])

        # Refreshing mid-test restores exact same question and option order
        st_t2, tdata2 = c1.request("GET", f"/api/test/{sid}")
        self.assertEqual(tdata2["current_question"]["id"], tdata["current_question"]["id"])
        self.assertEqual(tdata2["current_question"]["choices"], first_choices)

        # Verify rules on the frozen items in DB: 10 questions, same chapter, <=2 matching, no duplicate facts
        con = raavi_db.connect_db(self.db_path)
        try:
            srow = con.execute("SELECT items_json FROM test_sessions WHERE id=?", (sid,)).fetchone()
            frozen = json.loads(srow["items_json"])
            self.assertEqual(len(frozen), 10)
            matching_cnt = 0
            facts_seen = set()
            for item in frozen:
                qv = con.execute(
                    "SELECT * FROM question_versions WHERE question_id=? AND version=?",
                    (item["id"], item["version"]),
                ).fetchone()
                self.assertEqual(qv["chapter"], "Uprising of 1857")
                if qv["question_type"] == "matching":
                    matching_cnt += 1
                fset = set(json.loads(qv["underlying_facts_json"]))
                self.assertFalse(fset & facts_seen, "Duplicate underlying fact in same session!")
                facts_seen |= fset
            self.assertLessEqual(matching_cnt, 2)

            # Look up exact keys for controlled grading test (5 correct, 3 incorrect, 2 skipped = 5/10)
            keys = []
            choices_per_q = []
            for item in frozen:
                qv = con.execute(
                    "SELECT answer_key, choices_json FROM question_versions WHERE question_id=? AND version=?",
                    (item["id"], item["version"]),
                ).fetchone()
                keys.append(qv["answer_key"])
                choices_per_q.append(json.loads(qv["choices_json"]))
        finally:
            con.close()

        # Answer Q1 correctly, then attempt duplicate submission on Q1 -> must not alter score or progress
        st_a1, a1 = c1.request(
            "POST",
            f"/api/test/{sid}/answer",
            {"question_index": 0, "response": keys[0], "skip": False},
        )
        self.assertEqual(st_a1, 200)
        self.assertTrue(a1["is_correct"])

        st_dup, dup_res = c1.request(
            "POST",
            f"/api/test/{sid}/answer",
            {"question_index": 0, "response": keys[0], "skip": False},
        )
        self.assertEqual(st_dup, 200)
        self.assertTrue(dup_res["already_submitted"])

        # Refresh mid-test -> resumes at Question 2 (index 1)
        st_resm, rdata = c1.request("GET", f"/api/test/{sid}")
        self.assertEqual(rdata["current_question"]["number"], 2)

        # Q2..Q5 correct (total 5 correct), Q6..Q8 incorrect (3 incorrect), Q9..Q10 skipped (2 skipped)
        for idx in range(1, 5):
            st_ok, ans = c1.request(
                "POST",
                f"/api/test/{sid}/answer",
                {"question_index": idx, "response": keys[idx], "skip": False},
            )
            self.assertTrue(ans["is_correct"])
        for idx in range(5, 8):
            wrong = next(ch for ch in choices_per_q[idx] if ch != keys[idx])
            st_bad, ans = c1.request(
                "POST",
                f"/api/test/{sid}/answer",
                {"question_index": idx, "response": wrong, "skip": False},
            )
            self.assertFalse(ans["is_correct"])
            self.assertFalse(ans["is_skip"])
        for idx in range(8, 10):
            st_sk, ans = c1.request(
                "POST",
                f"/api/test/{sid}/answer",
                {"question_index": idx, "response": None, "skip": True},
            )
            self.assertTrue(ans["is_skip"])
            if idx == 9:
                self.assertTrue(ans["completed"])
                report1 = ans["report"]

        self.assertEqual(report1["score"], 5)
        self.assertEqual(report1["total"], 10)
        self.assertEqual(len(report1["outcomes"]), 10)
        self.assertTrue(report1["is_first_attempt"])

        # Cross-student isolation: student2 cannot read student1's report
        c2 = HttpClient(self.base_url)
        self._register_and_verify(c2, "other@example.com")
        st_forbidden, _ = c2.request("GET", f"/api/reports/{report1['id']}")
        self.assertEqual(st_forbidden, 404)

        # Verify History cooldown is active across the subject while Geography remains available
        st_sub, sub_data = c1.request("GET", "/api/subjects")
        self.assertEqual(st_sub, 200)
        self.assertFalse(sub_data["subjects"]["History"]["available"])
        self.assertGreater(sub_data["subjects"]["History"]["cooldown_seconds"], 80000)

        # Backdate History start by 25 hours to test cooldown expiry + second comparable attempt
        con = raavi_db.connect_db(self.db_path)
        try:
            con.execute(
                "UPDATE test_sessions SET started_at = started_at - 90000 WHERE id = ?",
                (sid,),
            )
            # Also mutate current question v2 in questions/question_versions to verify report1 stays untouched!
            first_qid = frozen[0]["id"]
            con.execute("UPDATE questions SET stem='EDITED STEM', current_version=2 WHERE id=?", (first_qid,))
            con.commit()
        finally:
            con.close()

        # Re-open report1 -> still shows original frozen stem, not 'EDITED STEM'
        st_r1, reopened = c1.request("GET", f"/api/reports/{report1['id']}")
        self.assertEqual(st_r1, 200)
        self.assertNotEqual(reopened["report"]["outcomes"][0]["stem"], "EDITED STEM")

        # Start second attempt in Uprising of 1857 -> check comparable progress and incomplete Geography handling
        st_second, sec_res = c1.request(
            "POST",
            "/api/start-test",
            {"subject": "History", "chapter": "Uprising of 1857", "nonce": "nonce-h-2"},
        )
        self.assertEqual(st_second, 200, sec_res)
        sid2 = sec_res["session_id"]

        con = raavi_db.connect_db(self.db_path)
        try:
            frozen2 = json.loads(con.execute("SELECT items_json FROM test_sessions WHERE id=?", (sid2,)).fetchone()["items_json"])
            keys2 = [
                con.execute(
                    "SELECT answer_key FROM question_versions WHERE question_id=? AND version=?",
                    (item["id"], item["version"]),
                ).fetchone()["answer_key"]
                for item in frozen2
            ]
        finally:
            con.close()

        for idx in range(10):
            _, a = c1.request(
                "POST",
                f"/api/test/{sid2}/answer",
                {"question_index": idx, "response": keys2[idx], "skip": False},
            )
        report2 = a["report"]
        self.assertEqual(report2["score"], 10)
        self.assertFalse(report2["is_first_attempt"])
        self.assertEqual(report2["delta"], 5)
        self.assertEqual(len(report2["comparable_history"]), 2)

        # Backdate Geography unfinished session >24h -> unfinished_blocking_new must block new start until ended
        geo_sid = res_geo["session_id"]
        con = raavi_db.connect_db(self.db_path)
        try:
            con.execute("UPDATE test_sessions SET started_at = started_at - 90000 WHERE id=?", (geo_sid,))
            con.commit()
        finally:
            con.close()

        st_gs, gs_data = c1.request("GET", "/api/subjects")
        self.assertTrue(gs_data["subjects"]["Geography"]["unfinished_blocking_new"])
        st_blk, blk_err = c1.request(
            "POST",
            "/api/start-test",
            {"subject": "Geography", "chapter": "Climate", "nonce": "geo-blk"},
        )
        self.assertEqual(st_blk, 409)
        self.assertEqual(blk_err["code"], "unfinished_exists")

        # End Geography unfinished test as incomplete -> excluded from completed trends, allows new Geography start
        st_end, end_res = c1.request("POST", f"/api/test/{geo_sid}/end-incomplete", {})
        self.assertEqual(st_end, 200)
        self.assertEqual(end_res["report"]["status"], "incomplete")

        st_new_geo, new_geo = c1.request(
            "POST",
            "/api/start-test",
            {"subject": "Geography", "chapter": "Climate", "nonce": "geo-after-incomplete"},
        )
        self.assertEqual(st_new_geo, 200, new_geo)

        # Map asset serving check + missing asset check
        st_map, map_bytes, map_ct = c1.get_bytes("/assets/city-pins.png")
        self.assertEqual(st_map, 200)
        self.assertTrue(map_ct.startswith("image/png"))
        self.assertGreater(len(map_bytes), 1000)

        st_missing, _ = c1.request("GET", "/assets/nonexistent.png")
        self.assertEqual(st_missing, 404)

    def test_04_production_mail_unavailable_and_short_answer_normalization(self):
        # Short answer deterministic normalization
        item = {"question_type": "short_answer", "answer_key": "1940", "accepted_answers": ["1940", "14 August 1947", "50 km"]}
        self.assertEqual(raavi_engine.grade_response(item, "  1940  "), (True, False))
        self.assertEqual(raavi_engine.grade_response(item, "14   august 1947"), (True, False))
        self.assertEqual(raavi_engine.grade_response(item, "50 m"), (False, False))
        self.assertEqual(raavi_engine.grade_response(item, "   "), (False, True))

        # Production without SMTP returns 503 recoverable error
        prev_env = os.environ.get("RAAVI_ENV")
        os.environ["RAAVI_ENV"] = "production"
        try:
            c = HttpClient(self.base_url)
            st, err = c.request("POST", "/api/auth/register", {"email": "prodtest@example.com", "password": "Password123"})
            self.assertEqual(st, 503, err)
            self.assertIn("Email service", err["error"])
        finally:
            if prev_env is not None:
                os.environ["RAAVI_ENV"] = prev_env
            else:
                os.environ.pop("RAAVI_ENV", None)

    def test_03_exhausted_chapter_consumes_no_allowance(self):
        c = HttpClient(self.base_url)
        user = self._register_and_verify(c, "exhaust@example.com")

        # Lock all families in 'Minerals' for this user so 10 questions cannot be assembled
        con = raavi_db.connect_db(self.db_path)
        try:
            fams = [r["family"] for r in con.execute("SELECT DISTINCT family FROM questions WHERE chapter='Minerals'").fetchall()]
            future = time.time() + 86400 * 30
            con.executemany(
                "INSERT INTO family_lockouts(student_id, family, locked_until) VALUES (?, ?, ?)",
                [(user["id"], f, future) for f in fams],
            )
            con.commit()
        finally:
            con.close()

        st, err = c.request(
            "POST",
            "/api/start-test",
            {"subject": "Geography", "chapter": "Minerals", "nonce": "exh-1"},
        )
        self.assertEqual(st, 409)
        self.assertEqual(err["code"], "insufficient_questions")

        # Verify Geography allowance is STILL available!
        st_s, sdata = c.request("GET", "/api/subjects")
        self.assertTrue(sdata["subjects"]["Geography"]["available"])
        self.assertEqual(sdata["subjects"]["Geography"]["cooldown_seconds"], 0)

        # And another Geography chapter can start right away!
        st_ok, ok_res = c.request(
            "POST",
            "/api/start-test",
            {"subject": "Geography", "chapter": "Topography", "nonce": "exh-2"},
        )
        self.assertEqual(st_ok, 200, ok_res)


if __name__ == "__main__":
    unittest.main(verbosity=2)
