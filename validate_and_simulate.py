"""Reproducible bank import validation and chapter capacity simulation for RAAVi."""
from __future__ import annotations

import json
import random
from pathlib import Path

from raavi_bank import CHAPTERS, CHAT_PRACTICE_DIR, load_and_validate_bank
from raavi_engine import (
    DAY_SECONDS,
    LOCKOUT_SECONDS,
    InsufficientQuestionsError,
    select_questions_from_pool,
)

ROOT = Path(__file__).resolve().parent


def to_engine_pool(items: list[dict]) -> dict[tuple[str, str], list[dict]]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for item in items:
        if item["auto_status"] != "passed":
            continue
        grouped.setdefault((item["subject"], item["chapter"]), []).append(
            {
                "id": item["id"],
                "family": item["family"],
                "subject": item["subject"],
                "chapter": item["chapter"],
                "subtopic": item["subtopic"],
                "skill": item["skill"],
                "question_type": item["question_type"],
                "refs": item["refs"],
                "stem": item["stem"],
                "choices": item["choices"],
                "answer_key": item["key"],
                "explanation": item["why"],
                "map_asset": item["map_asset"],
                "underlying_facts": item["underlying_facts"],
                "version": 1,
            }
        )
    return grouped


def simulate_same_chapter(pool: list[dict], chapter: str, max_days: int = 184, seed: int = 42) -> dict:
    rng = random.Random(f"same-{chapter}-{seed}")
    locked_families: dict[str, float] = {}
    fact_last_seen: dict[str, float] = {}
    days_completed = 0
    failure_reason = ""
    t0 = 1_700_000_000.0

    for day in range(max_days):
        now = t0 + day * DAY_SECONDS
        active_locks = {fam: until for fam, until in locked_families.items() if until > now}
        try:
            selected = select_questions_from_pool(pool, active_locks, fact_last_seen, now, rng, chapter)
        except InsufficientQuestionsError as exc:
            failure_reason = str(exc)
            break
        days_completed += 1
        for q in selected:
            locked_families[q["family"]] = now + LOCKOUT_SECONDS
            for f in q["underlying_facts"]:
                fact_last_seen[f] = now

    return {
        "chapter": chapter,
        "days_completed": days_completed,
        "reached_62": days_completed >= 62,
        "reached_184": days_completed >= 184,
        "failure_reason": failure_reason,
    }


def simulate_rotating_subject(
    grouped: dict[tuple[str, str], list[dict]], subject: str, max_days: int = 184, seed: int = 42
) -> dict:
    chapters = CHAPTERS[subject]
    rng = random.Random(f"rotate-{subject}-{seed}")
    locked_families: dict[str, float] = {}
    fact_last_seen: dict[str, float] = {}
    t0 = 1_700_000_000.0
    days_completed = 0
    per_chapter_tests = {ch: 0 for ch in chapters}
    first_shortage = None

    for day in range(max_days):
        ch = chapters[day % len(chapters)]
        now = t0 + day * DAY_SECONDS
        active_locks = {fam: until for fam, until in locked_families.items() if until > now}
        try:
            selected = select_questions_from_pool(
                grouped[(subject, ch)], active_locks, fact_last_seen, now, rng, ch
            )
        except InsufficientQuestionsError as exc:
            first_shortage = {"day": day + 1, "chapter": ch, "reason": str(exc)}
            break
        days_completed += 1
        per_chapter_tests[ch] += 1
        for q in selected:
            locked_families[q["family"]] = now + LOCKOUT_SECONDS
            for f in q["underlying_facts"]:
                fact_last_seen[f] = now

    return {
        "subject": subject,
        "days_completed": days_completed,
        "reached_184": days_completed >= 184,
        "first_shortage": first_shortage,
        "per_chapter_tests": per_chapter_tests,
    }


def generate_reports() -> tuple[dict, dict]:
    items, summary = load_and_validate_bank()
    grouped = to_engine_pool(items)

    # Validation report
    v_lines = [
        "# RAAVi Question Bank Validation & Inventory Report",
        "",
        f"- **Total cards imported:** {summary['total_imported']}",
        f"- **Passed automated validation:** {summary['auto_passed']}",
        f"- **Flagged by automated validation:** {summary['auto_flagged']}",
        f"- **Source family ID collisions detected:** {len(summary['source_id_collisions'])}",
        "",
        "## Subject Composition",
        "",
        "| Subject | Standalone | Timeline (Event Ordering) | Matching | Total | Unique Families |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for subj in ("History", "Geography"):
        s = summary["by_subject"][subj]
        v_lines.append(
            f"| {subj} | {s['standalone']} | {s['timeline']} | {s['matching']} | {s['total']} | {s['unique_families']} |"
        )

    v_lines += [
        "",
        "## Automated Checks & Editorial Review Separation",
        "",
        "- **Automated validation (`auto_status = passed`):** Verifies schema completeness, 4 distinct choices, valid answer key, non-empty explanation, valid source codes/pages, valid map asset paths (`city-pins.png`, `barrage-pins.png`), and matching topic-to-chapter mapping.",
        "- **Editorial / subject-accuracy review (`editorial_status`):** Kept separate from automated validation. `KH-*` items (228) are authored prompts still marked `authored_uncalibrated` until student response data supports difficulty calibration; generated `R-*`, `timeline-*`, and `matching-*` items (5,372) are marked `pending_editorial_review`.",
        "- **Anomalies detected in source files:**",
    ]
    for col in summary["source_id_collisions"]:
        v_lines.append(
            f"  - Duplicate source ID `{col['family']}` appears {col['count']} times in `chat-practice/questions.txt` (both prompts are distinct valid items; importer preserves source family `{col['family']}` and assigns disambiguated item ID `{col['family']}#2` to the second row)."
        )
    v_lines.append(
        "  - On `chat-practice/city-pins.png` (`M:3`), letters `R` (Rawalpindi, Rahim Yar Khan) and `S` (Swat, Sialkot) each appear twice on the figure; the 9 active map-pin items (`KH-142`..`KH-150`) only target unambiguous single-letter pins (`G, Q, H, L, P, M, I, J, K`)."
    )
    v_lines.append(
        "  - Legacy `bank.py` contains 30 prototype MCQs (15 History, 15 Geography) with no source page references; they are excluded from the verified bank pending source citations."
    )

    v_lines += [
        "",
        "## Chapter-by-Chapter Inventory",
        "",
        "| # | Subject | Chapter | Total | Auto Passed | Unique Families | Standalone | Timeline | Matching | Map Pin | Editorial Status |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for c in summary["chapters"]:
        ed_str = ", ".join(f"{k}: {v}" for k, v in sorted(c["editorial_status"].items()))
        v_lines.append(
            f"| {c['number']} | {c['subject']} | {c['chapter']} | {c['total_imported']} | {c['auto_passed']} | {c['unique_families']} | {c['standalone']} | {c['timeline']} | {c['matching']} | {c['map_pin']} | {ed_str} |"
        )

    (ROOT / "validation-report.md").write_text("\n".join(v_lines) + "\n", encoding="utf-8")

    # Capacity simulation
    same_results = []
    for c in summary["chapters"]:
        res = simulate_same_chapter(grouped[(c["subject"], c["chapter"])], c["chapter"], max_days=184)
        res["subject"] = c["subject"]
        res["number"] = c["number"]
        res["standalone"] = c["standalone"]
        res["timeline"] = c["timeline"]
        res["matching"] = c["matching"]
        res["non_matching"] = c["standalone"] + c["timeline"]
        same_results.append(res)

    rot_history = simulate_rotating_subject(grouped, "History", max_days=184)
    rot_geo = simulate_rotating_subject(grouped, "Geography", max_days=184)

    c_lines = [
        "# RAAVi Chapter Practice Capacity Simulation Report",
        "",
        "Simulation uses the live `select_questions_from_pool` selector with:",
        "- **10 questions per test** from one selected chapter",
        "- **62-day per-student family lockout**",
        "- **At most 2 matching items per 10-question test** (requiring at least 8 non-matching items per test)",
        "- **Zero duplicate underlying facts within any single 10-question test**",
        "",
        "## Key Findings",
        "",
        "- **Can the current bank promise 6 months (184 days) of fresh same-chapter practice?** **No.**",
        f"- **Minimum same-chapter capacity:** {min(r['days_completed'] for r in same_results)} day(s) ({min(same_results, key=lambda r: r['days_completed'])['chapter']}).",
        f"- **Maximum same-chapter capacity:** {max(r['days_completed'] for r in same_results)} day(s) ({max(same_results, key=lambda r: r['days_completed'])['chapter']}).",
        f"- **Rotating-chapter student (History, 16 chapters):** Sustained **{rot_history['days_completed']} consecutive daily tests** before first shortage"
        + (f" on day {rot_history['first_shortage']['day']} in `{rot_history['first_shortage']['chapter']}`." if rot_history["first_shortage"] else " (passed 184 days)."),
        f"- **Rotating-chapter student (Geography, 12 chapters):** Sustained **{rot_geo['days_completed']} consecutive daily tests** before first shortage"
        + (f" on day {rot_geo['first_shortage']['day']} in `{rot_geo['first_shortage']['chapter']}`." if rot_geo["first_shortage"] else " (passed 184 days)."),
        "",
        "Why same-chapter capacity is constrained even though each chapter has 200 cards:",
        "1. With at most 2 matching items per 10-question test, each test requires at least **8 non-matching items** (`standalone + timeline`). Most Geography chapters have only 19–25 standalone items and 0 timeline items, capping them at **2–3 tests** before running out of non-matching items.",
        "2. Even when timeline or standalone counts are higher, `timeline` and `matching` items combine underlying `R-*` recall facts. Requiring zero repeated facts inside a single test prevents combining cards that share the same underlying facts.",
        "3. Sustaining 62 days of daily same-chapter tests requires at least **496 non-matching unique-fact items** (62 × 8) and 620 total eligible non-overlapping families per chapter; 184 days requires at least **1,472 non-matching items** and 1,840 eligible families per chapter.",
        "",
        "## Same-Chapter Daily Practice Capacity (184-Day Test)",
        "",
        "| # | Subject | Chapter | Non-Matching (Standalone + Timeline) | Matching | Complete Daily Tests Sustained | Meets 62d? | Meets 184d? |",
        "|---:|---|---|---:|---:|---:|---|---|",
    ]
    for r in same_results:
        c_lines.append(
            f"| {r['number']} | {r['subject']} | {r['chapter']} | {r['non_matching']} ({r['standalone']}+{r['timeline']}) | {r['matching']} | {r['days_completed']} | {'Yes' if r['reached_62'] else 'No'} | {'Yes' if r['reached_184'] else 'No'} |"
        )

    c_lines += [
        "",
        "## Priority Chapters for New Question Writing",
        "",
        "Ranked by lowest same-chapter capacity first:",
        "",
    ]
    for r in sorted(same_results, key=lambda x: (x["days_completed"], x["non_matching"])):
        c_lines.append(
            f"- **{r['subject']} · {r['chapter']}**: sustains **{r['days_completed']}** test(s) ({r['standalone']} standalone, {r['timeline']} timeline)."
        )

    (ROOT / "capacity-report.md").write_text("\n".join(c_lines) + "\n", encoding="utf-8")
    return summary, {
        "same_chapter": same_results,
        "rotating_history": rot_history,
        "rotating_geography": rot_geo,
    }


if __name__ == "__main__":
    summary, sim = generate_reports()
    print(f"Validation complete: {summary['auto_passed']}/{summary['total_imported']} passed.")
    print(f"Rotating History: {sim['rotating_history']['days_completed']} days; Rotating Geography: {sim['rotating_geography']['days_completed']} days.")
    print("Same-chapter min/max:", min(r["days_completed"] for r in sim["same_chapter"]), max(r["days_completed"] for r in sim["same_chapter"]))
