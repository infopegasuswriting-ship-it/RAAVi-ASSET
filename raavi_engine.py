"""RAAVi core assessment engine: selection, 24h limits, 62-day repeat lockouts, marking, reports."""
from __future__ import annotations

import json
import math
import random
import re
import sqlite3
import time
from collections import Counter
from typing import Any

from raavi_bank import CHAPTERS, CHAPTER_INDEX, MAP_ASSETS

DAY_SECONDS = 86400
LOCKOUT_DAYS = 62
LOCKOUT_SECONDS = LOCKOUT_DAYS * DAY_SECONDS
FACT_SPACING_SECONDS = 7 * DAY_SECONDS
QUESTIONS_PER_TEST = 10
MAX_MATCHING_PER_TEST = 2


class EngineError(ValueError):
    def __init__(self, message: str, status: int = 400, code: str = "error"):
        super().__init__(message)
        self.status = status
        self.code = code


class InsufficientQuestionsError(EngineError):
    def __init__(self, chapter: str, available_count: int, reason: str):
        msg = (
            f"'{chapter}' does not currently have 10 eligible fresh questions available "
            f"({reason}). Please choose another chapter; your subject allowance was not used."
        )
        super().__init__(msg, status=409, code="insufficient_questions")
        self.chapter = chapter
        self.available_count = available_count


def normalize_short_answer(text: str) -> str:
    """
    Deterministic normalization for short-answer items:
    strips surrounding whitespace, collapses internal spaces, lowercases,
    while preserving meaningful differences in names, numbers, dates, and units.
    """
    s = text.strip().lower()
    s = s.replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)
    return s


def grade_response(item: dict[str, Any], response: str | None) -> tuple[bool, bool]:
    """Return (is_correct, is_skip)."""
    if response is None or (isinstance(response, str) and not response.strip()):
        return False, True
    qtype = item.get("question_type", "mcq")
    if qtype == "short_answer":
        accepted = item.get("accepted_answers") or [item["answer_key"]]
        norm_resp = normalize_short_answer(response)
        is_ok = any(norm_resp == normalize_short_answer(ans) for ans in accepted)
        return is_ok, False
    return response == item["answer_key"], False


def subject_availability(db: sqlite3.Connection, student_id: int, subject: str, now: float) -> dict[str, Any]:
    """Compute rolling 24h availability and active session state for a subject."""
    if subject not in CHAPTERS:
        raise EngineError("Invalid subject.")

    latest = db.execute(
        """
        SELECT started_at FROM test_sessions
        WHERE student_id = ? AND subject = ?
        ORDER BY started_at DESC LIMIT 1
        """,
        (student_id, subject),
    ).fetchone()

    active = db.execute(
        """
        SELECT id, chapter, started_at, current_index
        FROM test_sessions
        WHERE student_id = ? AND subject = ? AND status = 'active'
        ORDER BY started_at DESC LIMIT 1
        """,
        (student_id, subject),
    ).fetchone()

    cooldown_remaining = 0
    next_available_at = None
    if latest:
        unlock_at = latest["started_at"] + DAY_SECONDS
        if unlock_at > now:
            cooldown_remaining = max(1, math.ceil(unlock_at - now))
            next_available_at = unlock_at

    can_start_new = (cooldown_remaining == 0) and (active is None)
    # If cooldown expired while an active test is still unfinished, student must resume or end it first.
    unfinished_blocking_new = (cooldown_remaining == 0) and (active is not None)

    return {
        "subject": subject,
        "available": can_start_new,
        "cooldown_seconds": cooldown_remaining,
        "next_available_at": next_available_at,
        "server_now": now,
        "unfinished_blocking_new": unfinished_blocking_new,
        "active_session": (
            {
                "id": active["id"],
                "chapter": active["chapter"],
                "started_at": active["started_at"],
                "current_index": active["current_index"],
                "answered_count": active["current_index"],
                "total": QUESTIONS_PER_TEST,
            }
            if active
            else None
        ),
    }


def get_chapter_summaries(db: sqlite3.Connection, student_id: int, subject: str) -> list[dict[str, Any]]:
    """Return all chapters for a subject in KH order with latest score, attempts, and active flag."""
    if subject not in CHAPTERS:
        raise EngineError("Invalid subject.")

    completed_rows = db.execute(
        """
        SELECT id, chapter, score, total, completed_at
        FROM reports
        WHERE student_id = ? AND subject = ? AND status = 'completed'
        ORDER BY completed_at DESC, id DESC
        """,
        (student_id, subject),
    ).fetchall()

    active_rows = db.execute(
        """
        SELECT id, chapter, current_index, started_at
        FROM test_sessions
        WHERE student_id = ? AND subject = ? AND status = 'active'
        """,
        (student_id, subject),
    ).fetchall()
    active_by_ch = {r["chapter"]: dict(r) for r in active_rows}

    reports_by_ch: dict[str, list[sqlite3.Row]] = {}
    for r in completed_rows:
        reports_by_ch.setdefault(r["chapter"], []).append(r)

    bank_counts = {
        r["chapter"]: r["cnt"]
        for r in db.execute(
            "SELECT chapter, count(*) AS cnt FROM questions WHERE subject=? AND auto_status='passed' GROUP BY chapter",
            (subject,),
        ).fetchall()
    }

    result = []
    for idx, chapter in enumerate(CHAPTERS[subject], 1):
        reps = reports_by_ch.get(chapter, [])
        latest = reps[0] if reps else None
        previous = reps[1] if len(reps) > 1 else None
        active = active_by_ch.get(chapter)
        result.append(
            {
                "number": idx,
                "subject": subject,
                "chapter": chapter,
                "bank_count": bank_counts.get(chapter, 0),
                "completed_attempts": len(reps),
                "latest_report_id": latest["id"] if latest else None,
                "latest_score": latest["score"] if latest else None,
                "latest_total": latest["total"] if latest else QUESTIONS_PER_TEST,
                "latest_completed_at": latest["completed_at"] if latest else None,
                "previous_score": previous["score"] if previous else None,
                "active_session": (
                    {
                        "id": active["id"],
                        "current_index": active["current_index"],
                        "started_at": active["started_at"],
                    }
                    if active
                    else None
                ),
            }
        )
    return result


def select_questions_from_pool(
    pool: list[dict[str, Any]],
    locked_families: dict[str, float],
    fact_last_seen: dict[str, float],
    now: float,
    rng: random.Random,
    chapter: str,
) -> list[dict[str, Any]]:
    """
    Pure selection algorithm (shared between live server and capacity simulator).
    Selects exactly 10 eligible questions from one chapter enforcing:
    1. 62-day family lockout (locked_families contains families locked until > now).
    2. At most MAX_MATCHING_PER_TEST (2) matching items per 10-question test.
    3. No underlying fact repeated within the same 10-question test.
    4. Prefer unseen families, less-recently-seen component facts, standalone over generated,
       and subtopic/skill diversity.
    """
    eligible = [q for q in pool if q["family"] not in locked_families]
    if len(eligible) < QUESTIONS_PER_TEST:
        raise InsufficientQuestionsError(
            chapter,
            len(eligible),
            f"only {len(eligible)} eligible question(s) remain outside the 62-day repeat lockout",
        )

    # Shuffle first for random tie-breaking
    shuffled = list(eligible)
    rng.shuffle(shuffled)

    non_matching = [q for q in shuffled if q["question_type"] != "matching"]
    matching = [q for q in shuffled if q["question_type"] == "matching"]

    if len(non_matching) + min(len(matching), MAX_MATCHING_PER_TEST) < QUESTIONS_PER_TEST:
        raise InsufficientQuestionsError(
            chapter,
            len(non_matching) + min(len(matching), MAX_MATCHING_PER_TEST),
            "not enough non-matching questions to meet the maximum 2 matching items rule",
        )

    selected: list[dict[str, Any]] = []
    used_facts: set[str] = set()
    used_families: set[str] = set()
    subtopic_counts: Counter[str] = Counter()
    skill_counts: Counter[str] = Counter()
    matching_count = 0

    def is_compatible(q: dict[str, Any]) -> bool:
        if q["family"] in used_families:
            return False
        if q["question_type"] == "matching" and matching_count >= MAX_MATCHING_PER_TEST:
            return False
        q_facts = set(q["underlying_facts"])
        if q_facts & used_facts:
            return False
        return True

    def score_candidate(q: dict[str, Any]) -> tuple:
        q_facts = q["underlying_facts"]
        never_seen_family = 0 if q["family"] not in fact_last_seen else 1
        latest_fact = max((fact_last_seen.get(f, 0.0) for f in q_facts), default=0.0)
        recent_fact_penalty = 1 if latest_fact > (now - FACT_SPACING_SECONDS) else 0
        # Format priority: 0 = standalone MCQ/chronology/map, 1 = timeline, 2 = matching
        if q["question_type"] == "matching":
            format_rank = 2
        elif q["question_type"] == "timeline":
            format_rank = 1
        else:
            format_rank = 0
        return (
            format_rank,
            recent_fact_penalty,
            never_seen_family,
            subtopic_counts[q["subtopic"]],
            skill_counts[q["skill"]],
            latest_fact,
        )

    # Greedy selection with backtracking fallback if a greedy choice blocks reaching 10
    candidates = list(shuffled)
    for _ in range(QUESTIONS_PER_TEST):
        valid = [q for q in candidates if is_compatible(q)]
        if not valid:
            break
        # Pick best candidate; if multiple non-matching exist, prefer non-matching first
        chosen = min(valid, key=score_candidate)
        selected.append(chosen)
        candidates.remove(chosen)
        used_families.add(chosen["family"])
        used_facts.update(chosen["underlying_facts"])
        subtopic_counts[chosen["subtopic"]] += 1
        skill_counts[chosen["skill"]] += 1
        if chosen["question_type"] == "matching":
            matching_count += 1

    if len(selected) < QUESTIONS_PER_TEST:
        # Backtracking search (bounded) to verify whether a valid 10-item subset exists at all
        ordered = sorted(shuffled, key=score_candidate)
        found: list[dict[str, Any]] | None = None
        steps = 0
        max_steps = 25000

        def backtrack(idx: int, cur: list[dict[str, Any]], cur_facts: set[str], cur_fams: set[str], m_cnt: int) -> bool:
            nonlocal found, steps
            steps += 1
            if steps > max_steps:
                return False
            if len(cur) == QUESTIONS_PER_TEST:
                found = list(cur)
                return True
            if idx >= len(ordered) or len(cur) + (len(ordered) - idx) < QUESTIONS_PER_TEST:
                return False
            for j in range(idx, len(ordered)):
                if steps > max_steps:
                    return False
                q = ordered[j]
                if q["family"] in cur_fams:
                    continue
                if q["question_type"] == "matching" and m_cnt >= MAX_MATCHING_PER_TEST:
                    continue
                qf = set(q["underlying_facts"])
                if qf & cur_facts:
                    continue
                cur.append(q)
                if backtrack(j + 1, cur, cur_facts | qf, cur_fams | {q["family"]}, m_cnt + (1 if q["question_type"] == "matching" else 0)):
                    return True
                cur.pop()
            return False

        # Bound backtracking iterations so worst-case doesn't stall
        backtrack(0, [], set(), set(), 0)
        if found is None:
            raise InsufficientQuestionsError(
                chapter,
                len(selected),
                "remaining eligible questions share overlapping facts or exceed the 2-matching-item limit",
            )
        selected = found

    rng.shuffle(selected)
    return selected


def _load_chapter_pool(db: sqlite3.Connection, subject: str, chapter: str) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT id, family, subject, chapter, subtopic, skill, question_type,
               refs, stem, choices_json, answer_key, explanation, map_asset,
               underlying_facts_json, current_version
        FROM questions
        WHERE subject = ? AND chapter = ? AND auto_status = 'passed'
        """,
        (subject, chapter),
    ).fetchall()
    pool = []
    for r in rows:
        pool.append(
            {
                "id": r["id"],
                "family": r["family"],
                "subject": r["subject"],
                "chapter": r["chapter"],
                "subtopic": r["subtopic"],
                "skill": r["skill"],
                "question_type": r["question_type"],
                "refs": r["refs"],
                "stem": r["stem"],
                "choices": json.loads(r["choices_json"]),
                "answer_key": r["answer_key"],
                "explanation": r["explanation"],
                "map_asset": r["map_asset"],
                "underlying_facts": json.loads(r["underlying_facts_json"]),
                "version": r["current_version"],
            }
        )
    return pool


def start_chapter_test(
    db: sqlite3.Connection,
    student_id: int,
    subject: str,
    chapter: str,
    nonce: str,
    now: float,
) -> dict[str, Any]:
    """
    Atomically create a 10-question chapter test session, reserve its families/facts,
    and record the subject start timestamp. Idempotent by (student_id, nonce).
    """
    if subject not in CHAPTERS:
        raise EngineError("Choose History or Geography.")
    if chapter not in CHAPTERS[subject]:
        raise EngineError("Choose a valid chapter for that subject.")
    if not nonce or len(nonce) > 128:
        raise EngineError("Missing start identifier.")

    db.execute("BEGIN IMMEDIATE")
    try:
        # 1. Idempotency check (double-click / retry / duplicate request)
        existing = db.execute(
            "SELECT id, subject, chapter FROM test_sessions WHERE student_id=? AND nonce=?",
            (student_id, nonce),
        ).fetchone()
        if existing:
            db.commit()
            return {"session_id": existing["id"], "subject": existing["subject"], "chapter": existing["chapter"], "idempotent": True}

        # 2. Check active unfinished session for this subject
        active = db.execute(
            "SELECT id, chapter, started_at FROM test_sessions WHERE student_id=? AND subject=? AND status='active'",
            (student_id, subject),
        ).fetchone()
        if active:
            if active["started_at"] + DAY_SECONDS <= now:
                raise EngineError(
                    f"You have an unfinished {subject} test in '{active['chapter']}'. Please resume it or end it before starting a new test.",
                    status=409,
                    code="unfinished_exists",
                )
            raise EngineError(
                f"You already have an active {subject} test in '{active['chapter']}'. Resume it to continue.",
                status=409,
                code="unfinished_exists",
            )

        # 3. Check rolling 24-hour subject allowance
        latest = db.execute(
            "SELECT started_at FROM test_sessions WHERE student_id=? AND subject=? ORDER BY started_at DESC LIMIT 1",
            (student_id, subject),
        ).fetchone()
        if latest and (latest["started_at"] + DAY_SECONDS) > now:
            rem = math.ceil((latest["started_at"] + DAY_SECONDS - now) / 60)
            h, m = divmod(rem, 60)
            raise EngineError(
                f"Limit reached. {h:02d}h {m:02d}m remaining until your next {subject} test.",
                status=429,
                code="cooldown_active",
            )

        # 4. Load pool, lockouts, and fact exposures
        pool = _load_chapter_pool(db, subject, chapter)
        locked_rows = db.execute(
            "SELECT family, locked_until FROM family_lockouts WHERE student_id=? AND locked_until > ?",
            (student_id, now),
        ).fetchall()
        locked_families = {r["family"]: r["locked_until"] for r in locked_rows}

        fact_rows = db.execute(
            "SELECT fact_id, last_seen_at FROM fact_exposures WHERE student_id=?",
            (student_id,),
        ).fetchall()
        fact_last_seen = {r["fact_id"]: r["last_seen_at"] for r in fact_rows}

        rng = random.SystemRandom()
        selected = select_questions_from_pool(pool, locked_families, fact_last_seen, now, rng, chapter)

        # 5. Freeze item versions, option orders, lockouts, and fact exposures atomically
        frozen_items = []
        option_orders = []
        for q in selected:
            opts = list(q["choices"])
            rng.shuffle(opts)
            frozen_items.append({"id": q["id"], "version": q["version"]})
            option_orders.append(opts)

        cursor = db.execute(
            """
            INSERT INTO test_sessions (
                student_id, subject, chapter, nonce, started_at, status,
                items_json, option_orders_json, current_index
            ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, 0)
            """,
            (
                student_id,
                subject,
                chapter,
                nonce,
                now,
                json.dumps(frozen_items, ensure_ascii=False),
                json.dumps(option_orders, ensure_ascii=False),
            ),
        )
        session_id = cursor.lastrowid

        lock_until = now + LOCKOUT_SECONDS
        for q in selected:
            db.execute(
                """
                INSERT INTO family_lockouts (student_id, family, locked_until)
                VALUES (?, ?, ?)
                ON CONFLICT(student_id, family) DO UPDATE SET
                    locked_until = MAX(family_lockouts.locked_until, excluded.locked_until)
                """,
                (student_id, q["family"], lock_until),
            )
            for fact_id in q["underlying_facts"]:
                db.execute(
                    """
                    INSERT INTO fact_exposures (student_id, fact_id, last_seen_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(student_id, fact_id) DO UPDATE SET
                        last_seen_at = MAX(fact_exposures.last_seen_at, excluded.last_seen_at)
                    """,
                    (student_id, fact_id, now),
                )

        db.commit()
        return {"session_id": session_id, "subject": subject, "chapter": chapter, "idempotent": False}
    except Exception:
        db.rollback()
        raise


def _load_frozen_version(db: sqlite3.Connection, qid: str, version: int) -> sqlite3.Row:
    row = db.execute(
        "SELECT * FROM question_versions WHERE question_id=? AND version=?",
        (qid, version),
    ).fetchone()
    if not row:
        raise EngineError(f"Question version {qid} v{version} not found.", status=500)
    return row


def get_test_state(db: sqlite3.Connection, student_id: int, session_id: int, now: float) -> dict[str, Any]:
    """
    Return test session state for the owning student.
    Never exposes answer keys or explanations for unanswered questions.
    """
    sess = db.execute(
        "SELECT * FROM test_sessions WHERE id=? AND student_id=?",
        (session_id, student_id),
    ).fetchone()
    if not sess:
        raise EngineError("Test session not found.", status=404)

    if sess["status"] != "active":
        return {
            "id": sess["id"],
            "status": sess["status"],
            "subject": sess["subject"],
            "chapter": sess["chapter"],
            "started_at": sess["started_at"],
            "completed_at": sess["completed_at"],
            "total": QUESTIONS_PER_TEST,
            "current_index": sess["current_index"],
            "report": get_report(db, student_id, session_id),
        }

    items_meta = json.loads(sess["items_json"])
    option_orders = json.loads(sess["option_orders_json"])
    responses = {
        r["question_index"]: r
        for r in db.execute(
            "SELECT * FROM test_responses WHERE test_session_id=? ORDER BY question_index",
            (session_id,),
        ).fetchall()
    }

    # Determine first unanswered question index
    first_unanswered = None
    for idx in range(len(items_meta)):
        if idx not in responses:
            first_unanswered = idx
            break

    if first_unanswered is None:
        # Edge case: all 10 answered but report wasn't finalized yet
        report = _finalize_session(db, sess, now, status="completed")
        db.commit()
        return {
            "id": sess["id"],
            "status": "completed",
            "subject": sess["subject"],
            "chapter": sess["chapter"],
            "started_at": sess["started_at"],
            "completed_at": report["completed_at"],
            "total": QUESTIONS_PER_TEST,
            "current_index": QUESTIONS_PER_TEST,
            "report": report,
        }

    meta = items_meta[first_unanswered]
    qv = _load_frozen_version(db, meta["id"], meta["version"])
    map_info = MAP_ASSETS.get(qv["map_asset"]) if qv["map_asset"] else None

    current_question = {
        "index": first_unanswered,
        "number": first_unanswered + 1,
        "total": len(items_meta),
        "id": qv["question_id"],
        "subtopic": qv["subtopic"],
        "skill": qv["skill"],
        "question_type": qv["question_type"],
        "stem": qv["stem"],
        "choices": option_orders[first_unanswered],
        "map_asset": qv["map_asset"],
        "map_info": map_info,
    }

    prior_outcomes = []
    for idx in range(first_unanswered):
        r = responses[idx]
        pq = _load_frozen_version(db, r["question_id"], r["question_version"])
        prior_outcomes.append(
            {
                "index": idx,
                "number": idx + 1,
                "stem": pq["stem"],
                "response": r["response"],
                "is_correct": bool(r["is_correct"]),
                "is_skip": bool(r["is_skip"]),
                "correct_answer": pq["answer_key"],
                "explanation": pq["explanation"],
                "refs": pq["refs"],
            }
        )

    return {
        "id": sess["id"],
        "status": sess["status"],
        "subject": sess["subject"],
        "chapter": sess["chapter"],
        "chapter_number": CHAPTER_INDEX.get((sess["subject"], sess["chapter"])),
        "started_at": sess["started_at"],
        "total": len(items_meta),
        "current_index": first_unanswered,
        "current_question": current_question,
        "prior_outcomes": prior_outcomes,
        "cooldown_expired": (sess["started_at"] + DAY_SECONDS) <= now,
    }


def _build_report_payload(db: sqlite3.Connection, sess: sqlite3.Row, report_row: sqlite3.Row) -> dict[str, Any]:
    items_meta = json.loads(sess["items_json"])
    option_orders = json.loads(sess["option_orders_json"])
    responses = {
        r["question_index"]: r
        for r in db.execute(
            "SELECT * FROM test_responses WHERE test_session_id=? ORDER BY question_index",
            (sess["id"],),
        ).fetchall()
    }

    outcomes = []
    for idx, meta in enumerate(items_meta):
        qv = _load_frozen_version(db, meta["id"], meta["version"])
        r = responses.get(idx)
        is_skip = True if r is None else bool(r["is_skip"])
        is_correct = False if r is None else bool(r["is_correct"])
        resp_text = None if r is None else r["response"]
        outcomes.append(
            {
                "number": idx + 1,
                "question_id": qv["question_id"],
                "question_version": qv["version"],
                "subtopic": qv["subtopic"],
                "skill": qv["skill"],
                "question_type": qv["question_type"],
                "stem": qv["stem"],
                "choices": option_orders[idx],
                "map_asset": qv["map_asset"],
                "student_response": resp_text,
                "is_correct": is_correct,
                "is_skip": is_skip,
                "status_label": "Correct" if is_correct else ("Skipped" if is_skip else "Incorrect"),
                "marks": 1 if is_correct else 0,
                "correct_answer": qv["answer_key"],
                "explanation": qv["explanation"],
                "refs": qv["refs"],
            }
        )

    # Comparable history: completed attempts in the same subject + chapter
    comparable_rows = db.execute(
        """
        SELECT id, score, total, completed_at
        FROM reports
        WHERE student_id = ? AND subject = ? AND chapter = ? AND status = 'completed'
        ORDER BY completed_at ASC, id ASC
        """,
        (sess["student_id"], sess["subject"], sess["chapter"]),
    ).fetchall()

    comparable_history = [
        {
            "report_id": cr["id"],
            "score": cr["score"],
            "total": cr["total"],
            "completed_at": cr["completed_at"],
            "is_current": cr["id"] == report_row["id"],
        }
        for cr in comparable_rows
    ]

    previous_comparable = None
    delta = None
    if report_row["status"] == "completed":
        idx_in_series = next((i for i, c in enumerate(comparable_history) if c["report_id"] == report_row["id"]), -1)
        if idx_in_series > 0:
            previous_comparable = comparable_history[idx_in_series - 1]
            delta = report_row["score"] - previous_comparable["score"]

    return {
        "id": report_row["id"],
        "test_session_id": sess["id"],
        "subject": sess["subject"],
        "chapter": sess["chapter"],
        "chapter_number": CHAPTER_INDEX.get((sess["subject"], sess["chapter"])),
        "status": report_row["status"],
        "score": report_row["score"],
        "total": report_row["total"],
        "started_at": sess["started_at"],
        "completed_at": report_row["completed_at"],
        "outcomes": outcomes,
        "comparable_attempts_count": len(comparable_history),
        "is_first_attempt": report_row["status"] == "completed" and len(comparable_history) == 1,
        "previous_comparable": previous_comparable,
        "delta": delta,
        "comparable_history": comparable_history,
    }


def _finalize_session(db: sqlite3.Connection, sess: sqlite3.Row, now: float, status: str) -> dict[str, Any]:
    existing_report = db.execute(
        "SELECT * FROM reports WHERE test_session_id=?",
        (sess["id"],),
    ).fetchone()
    if existing_report:
        return _build_report_payload(db, sess, existing_report)

    items_meta = json.loads(sess["items_json"])
    responses = {
        r["question_index"]: r
        for r in db.execute(
            "SELECT * FROM test_responses WHERE test_session_id=?",
            (sess["id"],),
        ).fetchall()
    }

    # For incomplete ending, record remaining unanswered items as skipped
    if status == "incomplete":
        for idx, meta in enumerate(items_meta):
            if idx not in responses:
                db.execute(
                    """
                    INSERT OR IGNORE INTO test_responses (
                        test_session_id, question_index, question_id, question_version,
                        response, is_correct, is_skip, submitted_at
                    ) VALUES (?, ?, ?, ?, NULL, 0, 1, ?)
                    """,
                    (sess["id"], idx, meta["id"], meta["version"], now),
                )

    score = db.execute(
        "SELECT COALESCE(SUM(is_correct), 0) FROM test_responses WHERE test_session_id=?",
        (sess["id"],),
    ).fetchone()[0]

    db.execute(
        "UPDATE test_sessions SET status=?, completed_at=?, current_index=? WHERE id=?",
        (status, now, len(items_meta), sess["id"]),
    )
    report_id = db.execute(
        """
        INSERT INTO reports (test_session_id, student_id, subject, chapter, status, score, total, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (sess["id"], sess["student_id"], sess["subject"], sess["chapter"], status, score, len(items_meta), now),
    ).lastrowid

    updated_sess = db.execute("SELECT * FROM test_sessions WHERE id=?", (sess["id"],)).fetchone()
    report_row = db.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    return _build_report_payload(db, updated_sess, report_row)


def submit_answer(
    db: sqlite3.Connection,
    student_id: int,
    session_id: int,
    question_index: int,
    response_raw: Any,
    skip: bool,
    now: float,
) -> dict[str, Any]:
    """
    Submit or skip one question. Final per question; repeated submissions cannot alter score
    or award extra credit. Returns immediate feedback, and completes report after Q10.
    """
    db.execute("BEGIN IMMEDIATE")
    try:
        sess = db.execute(
            "SELECT * FROM test_sessions WHERE id=? AND student_id=?",
            (session_id, student_id),
        ).fetchone()
        if not sess:
            raise EngineError("Test session not found.", status=404)
        if sess["status"] != "active":
            raise EngineError("This test session is already closed.", status=409)

        items_meta = json.loads(sess["items_json"])
        option_orders = json.loads(sess["option_orders_json"])
        if not isinstance(question_index, int) or not (0 <= question_index < len(items_meta)):
            raise EngineError("Invalid question index.")

        # Check if already answered (idempotency / tamper protection)
        prior = db.execute(
            "SELECT * FROM test_responses WHERE test_session_id=? AND question_index=?",
            (session_id, question_index),
        ).fetchone()
        if prior:
            qv = _load_frozen_version(db, prior["question_id"], prior["question_version"])
            # Return the original saved outcome without changing anything!
            report = None
            updated_sess = db.execute("SELECT * FROM test_sessions WHERE id=?", (session_id,)).fetchone()
            if updated_sess["status"] != "active":
                report = get_report(db, student_id, session_id)
            db.commit()
            return {
                "already_submitted": True,
                "question_index": question_index,
                "is_correct": bool(prior["is_correct"]),
                "is_skip": bool(prior["is_skip"]),
                "student_response": prior["response"],
                "correct_answer": qv["answer_key"],
                "explanation": qv["explanation"],
                "refs": qv["refs"],
                "completed": updated_sess["status"] != "active",
                "report": report,
            }

        # Ensure sequential progression: must answer the current lowest unanswered question
        answered_count = db.execute(
            "SELECT count(*) FROM test_responses WHERE test_session_id=?",
            (session_id,),
        ).fetchone()[0]
        if question_index != answered_count:
            raise EngineError(
                f"Please answer Question {answered_count + 1} first.",
                status=409,
            )

        meta = items_meta[question_index]
        qv = _load_frozen_version(db, meta["id"], meta["version"])

        if skip:
            clean_resp = None
        else:
            if not isinstance(response_raw, str) or not response_raw.strip():
                raise EngineError("Select an answer option or choose Skip.")
            clean_resp = response_raw if qv["question_type"] != "short_answer" else response_raw.strip()
            if qv["question_type"] != "short_answer":
                if clean_resp not in option_orders[question_index]:
                    raise EngineError("Invalid answer option.")

        is_correct, is_skip = grade_response(dict(qv), clean_resp)

        db.execute(
            """
            INSERT INTO test_responses (
                test_session_id, question_index, question_id, question_version,
                response, is_correct, is_skip, submitted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                question_index,
                qv["question_id"],
                qv["version"],
                clean_resp,
                1 if is_correct else 0,
                1 if is_skip else 0,
                now,
            ),
        )

        next_index = question_index + 1
        db.execute(
            "UPDATE test_sessions SET current_index=? WHERE id=?",
            (next_index, session_id),
        )

        report = None
        completed = next_index >= len(items_meta)
        if completed:
            report = _finalize_session(db, sess, now, status="completed")

        db.commit()
        return {
            "already_submitted": False,
            "question_index": question_index,
            "is_correct": is_correct,
            "is_skip": is_skip,
            "student_response": clean_resp,
            "correct_answer": qv["answer_key"],
            "explanation": qv["explanation"],
            "refs": qv["refs"],
            "completed": completed,
            "next_index": next_index,
            "report": report,
        }
    except Exception:
        db.rollback()
        raise


def end_unfinished_test(db: sqlite3.Connection, student_id: int, session_id: int, now: float) -> dict[str, Any]:
    """End an active unfinished test as incomplete so the student can start a newly eligible test."""
    db.execute("BEGIN IMMEDIATE")
    try:
        sess = db.execute(
            "SELECT * FROM test_sessions WHERE id=? AND student_id=?",
            (session_id, student_id),
        ).fetchone()
        if not sess:
            raise EngineError("Test session not found.", status=404)
        if sess["status"] != "active":
            report = get_report(db, student_id, session_id)
            db.commit()
            return report
        report = _finalize_session(db, sess, now, status="incomplete")
        db.commit()
        return report
    except Exception:
        db.rollback()
        raise


def list_reports(db: sqlite3.Connection, student_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT r.id, r.test_session_id, r.subject, r.chapter, r.status, r.score, r.total, r.completed_at,
               ts.started_at
        FROM reports r
        JOIN test_sessions ts ON ts.id = r.test_session_id
        WHERE r.student_id = ?
        ORDER BY r.completed_at DESC, r.id DESC
        """,
        (student_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_report(db: sqlite3.Connection, student_id: int, session_or_report_id: int) -> dict[str, Any]:
    report_row = db.execute(
        """
        SELECT * FROM reports
        WHERE student_id = ? AND (test_session_id = ? OR id = ?)
        LIMIT 1
        """,
        (student_id, session_or_report_id, session_or_report_id),
    ).fetchone()
    if not report_row:
        raise EngineError("Report not found.", status=404)
    sess = db.execute(
        "SELECT * FROM test_sessions WHERE id=? AND student_id=?",
        (report_row["test_session_id"], student_id),
    ).fetchone()
    if not sess:
        raise EngineError("Session not found.", status=404)
    return _build_report_payload(db, sess, report_row)
