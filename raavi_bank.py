"""RAAVi question bank import, validation, versioning, and inventory."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CHAT_PRACTICE_DIR = ROOT / "chat-practice"
DEFAULT_BANK_PATH = CHAT_PRACTICE_DIR / "practice-bank.jsonl"
DEFAULT_QUESTIONS_TXT = CHAT_PRACTICE_DIR / "questions.txt"
DEFAULT_RECALL_TXT = CHAT_PRACTICE_DIR / "recall-facts.txt"

# Canonical KH chapter order (matching chat-practice/practice.py)
CHAPTERS: dict[str, list[str]] = {
    "History": [
        "Mughal decline and British expansion",
        "Religious thinkers",
        "Uprising of 1857",
        "Sir Syed Ahmad Khan",
        "Urdu and regional languages",
        "Early Pakistan Movement",
        "Khilafat Movement",
        "Pakistan Movement, 1927–39",
        "Negotiations and partition, 1940–47",
        "Jinnah, Iqbal and Rahmat Ali",
        "Establishing Pakistan",
        "Stability and government after Jinnah",
        "Creation of Bangladesh",
        "Bhutto and Zia",
        "Governments, 1988–99",
        "International relations",
    ],
    "Geography": [
        "Topography",
        "Climate",
        "Water resources",
        "Forests",
        "Minerals",
        "Fishing",
        "Agriculture",
        "Power",
        "Industry",
        "Trade",
        "Transport and telecommunications",
        "Population and employment",
    ],
}

CHAPTER_INDEX: dict[tuple[str, str], int] = {
    (subj, ch): idx + 1
    for subj, ch_list in CHAPTERS.items()
    for idx, ch in enumerate(ch_list)
}

SOURCES: dict[str, str] = {
    "C27": "Cambridge O Level Pakistan Studies 2059, 2027 syllabus",
    "M": "MAP MARVELS",
    "X": "6 Mark Question Examples by KH",
    "S1": "SOLVED HISTORY SEC 1 NOTES BY KH",
    "S2": "SOLVED HISTORY SEC 2 NOTES BY KH",
    "S3": "SOLVED HISTORY SEC 3 NOTES BY KH",
    "H1": "Hist Book 1 UP",
    "H2": "Hist Book 2 UP",
    "H3": "Hist Book 3 UP",
    "G1": "Geo Book 1 UP",
    "G2": "Geo Book 2 UP",
}

# Topic-to-chapter ground truth from syllabus.py & practice.py
EXPECTED_CHAPTER_BY_TOPIC: dict[tuple[str, str], str] = {
    ("H", "Religious reform"): "Religious thinkers",
    ("H", "Mughal decline"): "Mughal decline and British expansion",
    ("H", "Company expansion"): "Mughal decline and British expansion",
    ("H", "1857 uprising"): "Uprising of 1857",
    ("H", "Aligarh"): "Sir Syed Ahmad Khan",
    ("H", "Languages"): "Urdu and regional languages",
    ("H", "Representation"): "Early Pakistan Movement",
    ("H", "Khilafat"): "Khilafat Movement",
    ("H", "Constitutional proposals"): "Pakistan Movement, 1927–39",
    ("H", "Transfer of power"): "Negotiations and partition, 1940–47",
    ("H", "Political ideas"): "Jinnah, Iqbal and Rahmat Ali",
    ("H", "Independence settlement"): "Establishing Pakistan",
    ("H", "Early ministries"): "Stability and government after Jinnah",
    ("H", "Agrarian reform"): "Stability and government after Jinnah",
    ("H", "East Pakistan"): "Creation of Bangladesh",
    ("H", "Bhutto and Zia"): "Bhutto and Zia",
    ("H", "Governments 1988–99"): "Governments, 1988–99",
    ("H", "Foreign relations"): "International relations",
    ("G", "Location"): "Topography",
    ("G", "Administrative areas and cities"): "Topography",
    ("G", "Relief"): "Topography",
    ("G", "Climate"): "Climate",
    ("G", "Water"): "Water resources",
    ("G", "Irrigation geography"): "Water resources",
    ("G", "Forests"): "Forests",
    ("G", "Minerals"): "Minerals",
    ("G", "Fishing"): "Fishing",
    ("G", "Agriculture"): "Agriculture",
    ("G", "Power"): "Power",
    ("G", "Industry"): "Industry",
    ("G", "Trade"): "Trade",
    ("G", "Trade institutions"): "Trade",
    ("G", "Transport"): "Transport and telecommunications",
    ("G", "Development"): "Transport and telecommunications",
    ("G", "Population"): "Population and employment",
}

MAP_ASSETS: dict[str, dict[str, str]] = {
    "city-pins.png": {
        "file": "city-pins.png",
        "ref": "M:3",
        "title": "Pakistan Major Cities Pin Map (Map Marvels p. 3)",
        "alt": "Outline map of Pakistan showing province boundaries and lettered red city pins.",
    },
    "barrage-pins.png": {
        "file": "barrage-pins.png",
        "ref": "M:5",
        "title": "Indus River Barrages Pin Map (Map Marvels p. 5)",
        "alt": "Map of the Indus river system with blue pins labelled A through F from upstream to downstream.",
    },
}


def subject_full(code_or_name: str) -> str:
    if code_or_name in ("H", "History"):
        return "History"
    if code_or_name in ("G", "Geography"):
        return "Geography"
    raise ValueError(f"Unknown subject: {code_or_name}")


def normalize_prompt(text: str) -> str:
    """Normalize prompt text to detect cosmetic rewrites / whitespace / punctuation duplicates."""
    s = text.lower().strip()
    s = s.replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s]", "", s)
    return s.strip()


def normalize_choice(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def resolve_map_asset(item: dict[str, Any]) -> str | None:
    """Resolve required map asset from skill/refs."""
    skill = item.get("skill", "")
    refs = item.get("refs", "")
    if skill == "map pin":
        if "M:3" in refs:
            return "city-pins.png"
        if "M:5" in refs:
            return "barrage-pins.png"
        return "__missing_map__"
    return None


def derive_question_type(item: dict[str, Any]) -> str:
    skill = item.get("skill", "")
    if skill == "matching":
        return "matching"
    if skill == "timeline":
        return "timeline"
    if skill == "map pin":
        return "map_pin"
    if skill == "chronology":
        return "chronology"
    return "mcq"


def derive_underlying_facts(item: dict[str, Any], stable_id: str) -> list[str]:
    """Return list of underlying fact IDs for exposure tracking."""
    comps = item.get("components")
    if isinstance(comps, list) and comps:
        return sorted(dict.fromkeys(str(c) for c in comps))
    return [item.get("family") or stable_id]


def content_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(
        {
            "subject": record["subject"],
            "chapter": record["chapter"],
            "topic": record["topic"],
            "skill": record["skill"],
            "question_type": record["question_type"],
            "refs": record["refs"],
            "stem": record["stem"],
            "choices": record["choices"],
            "key": record["key"],
            "why": record["why"],
            "map_asset": record["map_asset"],
            "family": record["family"],
            "underlying_facts": record["underlying_facts"],
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def load_and_validate_bank(
    bank_path: Path = DEFAULT_BANK_PATH,
    assets_dir: Path = CHAT_PRACTICE_DIR,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Parse practice-bank.jsonl, preserve stable IDs, detect anomalies,
    and produce a complete validation summary and chapter-by-chapter inventory.
    """
    raw_lines = [
        line for line in bank_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()
    ]
    raw_items = [json.loads(line) for line in raw_lines]

    # First pass: check exact/cosmetic duplicates and family ID collisions
    seen_families: Counter[str] = Counter()
    stem_occurrences: defaultdict[str, list[int]] = defaultdict(list)
    norm_stem_occurrences: defaultdict[str, list[int]] = defaultdict(list)

    for idx, item in enumerate(raw_items):
        fam = str(item.get("family", "")).strip()
        if fam:
            seen_families[fam] += 1
        stem = str(item.get("stem", ""))
        stem_occurrences[stem].append(idx)
        norm_stem_occurrences[normalize_prompt(stem)].append(idx)

    # Track sequential occurrences of duplicate family strings so every imported item gets a unique stable ID
    # while preserving its original family string as source_family!
    family_seq: Counter[str] = Counter()
    issues: list[dict[str, Any]] = []
    processed: list[dict[str, Any]] = []

    for idx, item in enumerate(raw_items):
        row_num = idx + 1
        raw_family = str(item.get("family", "")).strip()
        family_seq[raw_family] += 1
        if seen_families[raw_family] > 1 and family_seq[raw_family] > 1:
            stable_id = f"{raw_family}#{family_seq[raw_family]}"
        else:
            stable_id = raw_family or f"ITEM-{row_num:04d}"

        subj_code = str(item.get("subject", "")).strip()
        subj_name = "History" if subj_code == "H" else "Geography" if subj_code == "G" else ""
        chapter = str(item.get("chapter", "")).strip()
        topic = str(item.get("topic", "")).strip()
        skill = str(item.get("skill", "")).strip()
        refs = str(item.get("refs", "")).strip()
        stem = str(item.get("stem", "")).strip()
        key = str(item.get("key", ""))
        choices = item.get("choices", [])
        why = str(item.get("why", "")).strip()
        map_asset = resolve_map_asset(item)
        q_type = derive_question_type(item)
        facts = derive_underlying_facts(item, stable_id)

        item_flags: list[str] = []

        # 1. Schema & required fields
        if subj_name not in CHAPTERS:
            item_flags.append(f"invalid_subject:{subj_code}")
        elif chapter not in CHAPTERS[subj_name]:
            item_flags.append(f"unknown_chapter:{chapter}")

        # 2. Wrong chapter assignment check against topic mapping
        expected_ch = EXPECTED_CHAPTER_BY_TOPIC.get((subj_code, topic))
        if expected_ch is None:
            item_flags.append(f"unknown_topic:{topic}")
        elif expected_ch != chapter:
            item_flags.append(f"wrong_chapter:expected={expected_ch},got={chapter}")

        # 3. Duplicate prompt / cosmetic rewrite detection
        if len(stem_occurrences[str(item.get("stem", ""))]) > 1:
            item_flags.append("duplicate_exact_prompt")
        elif len(norm_stem_occurrences[normalize_prompt(stem)]) > 1:
            item_flags.append("cosmetic_rewrite_prompt")

        # 4. Duplicate family ID warning (e.g. KH-001, KH-126 in questions.txt)
        if seen_families[raw_family] > 1:
            item_flags.append(f"duplicate_source_family_id:{raw_family}")

        # 5. Repeated answer choices / ambiguous keys
        if not isinstance(choices, list) or len(choices) != 4:
            item_flags.append("invalid_choice_count")
        else:
            if len(set(choices)) != 4:
                item_flags.append("repeated_answer_choices")
            norm_choices = [normalize_choice(str(c)) for c in choices]
            if len(set(norm_choices)) != 4:
                item_flags.append("ambiguous_normalized_choices")
            if key not in choices:
                item_flags.append("key_not_in_choices")
            elif sum(1 for c in norm_choices if c == normalize_choice(key)) > 1:
                item_flags.append("ambiguous_key_match")

        # 6. Missing source references or unknown source codes
        if not refs:
            item_flags.append("missing_source_ref")
        else:
            for ref in refs.split(";"):
                ref = ref.strip()
                if ":" not in ref:
                    item_flags.append(f"malformed_ref:{ref}")
                else:
                    src_code, page = ref.split(":", 1)
                    if src_code not in SOURCES or not page.strip():
                        item_flags.append(f"unknown_source_ref:{ref}")

        # 7. Missing explanation
        if not why:
            item_flags.append("missing_explanation")

        # 8. Broken map reference
        if map_asset == "__missing_map__":
            item_flags.append("missing_map_reference")
        elif map_asset is not None:
            if not (assets_dir / map_asset).is_file():
                item_flags.append(f"broken_map_asset:{map_asset}")

        # 9. Matching internal duplicate fact check
        if "components" in item and isinstance(item["components"], list):
            if len(set(item["components"])) != len(item["components"]):
                item_flags.append("duplicate_component_fact_in_item")

        # Automated validation vs editorial subject review
        # Note: duplicate_source_family_id on KH-001 / KH-126 is flagged for ID hygiene,
        # while the two questions themselves are distinct valid prompts if disambiguated.
        blocking_flags = [
            f for f in item_flags if not f.startswith("duplicate_source_family_id:")
        ]
        auto_status = "flagged" if blocking_flags else "passed"

        # Editorial review status:
        # Standalone KH-* items are author-written; R-*, timeline-*, matching-* are generated
        # and have not yet undergone formal examiner-level calibration/subject audit.
        if raw_family.startswith("KH-"):
            editorial_status = "authored_uncalibrated"
        else:
            editorial_status = "pending_editorial_review"

        if item_flags:
            issues.append(
                {
                    "row": row_num,
                    "id": stable_id,
                    "family": raw_family,
                    "subject": subj_name,
                    "chapter": chapter,
                    "flags": item_flags,
                    "stem": stem[:120],
                }
            )

        rec = {
            "id": stable_id,
            "family": raw_family,
            "subject": subj_name,
            "chapter": chapter,
            "subtopic": topic,
            "topic": topic,
            "skill": skill,
            "question_type": q_type,
            "refs": refs,
            "stem": stem,
            "choices": choices,
            "key": key,
            "why": why,
            "map_asset": map_asset,
            "underlying_facts": facts,
            "auto_status": auto_status,
            "editorial_status": editorial_status,
            "validation_flags": item_flags,
        }
        rec["content_hash"] = content_hash(rec)
        processed.append(rec)

    # Build chapter-by-chapter inventory
    chapter_inventory: list[dict[str, Any]] = []
    for subj in ("History", "Geography"):
        for idx, ch in enumerate(CHAPTERS[subj], 1):
            ch_items = [r for r in processed if r["subject"] == subj and r["chapter"] == ch]
            passed = [r for r in ch_items if r["auto_status"] == "passed"]
            families = {r["family"] for r in passed}
            formats = Counter(r["question_type"] for r in passed)
            skills = Counter(r["skill"] for r in passed)
            editorial = Counter(r["editorial_status"] for r in passed)
            standalone_cnt = sum(
                1 for r in passed if r["question_type"] not in ("matching", "timeline")
            )
            timeline_cnt = formats.get("timeline", 0)
            matching_cnt = formats.get("matching", 0)
            map_cnt = formats.get("map_pin", 0)
            chapter_inventory.append(
                {
                    "number": idx,
                    "subject": subj,
                    "chapter": ch,
                    "total_imported": len(ch_items),
                    "auto_passed": len(passed),
                    "auto_flagged": len(ch_items) - len(passed),
                    "unique_families": len(families),
                    "standalone": standalone_cnt,
                    "timeline": timeline_cnt,
                    "matching": matching_cnt,
                    "map_pin": map_cnt,
                    "formats": dict(formats),
                    "skills": dict(skills),
                    "editorial_status": dict(editorial),
                    "duplicate_family_flags": sum(
                        1
                        for r in ch_items
                        if any(f.startswith("duplicate_source_family_id") for f in r["validation_flags"])
                    ),
                }
            )

    summary = {
        "total_imported": len(processed),
        "auto_passed": sum(1 for r in processed if r["auto_status"] == "passed"),
        "auto_flagged": sum(1 for r in processed if r["auto_status"] == "flagged"),
        "source_id_collisions": [
            {"family": fam, "count": cnt}
            for fam, cnt in seen_families.items()
            if cnt > 1
        ],
        "issues": issues,
        "chapters": chapter_inventory,
        "by_subject": {
            subj: {
                "total": sum(c["total_imported"] for c in chapter_inventory if c["subject"] == subj),
                "standalone": sum(c["standalone"] for c in chapter_inventory if c["subject"] == subj),
                "timeline": sum(c["timeline"] for c in chapter_inventory if c["subject"] == subj),
                "matching": sum(c["matching"] for c in chapter_inventory if c["subject"] == subj),
                "unique_families": sum(c["unique_families"] for c in chapter_inventory if c["subject"] == subj),
            }
            for subj in ("History", "Geography")
        },
    }
    return processed, summary


def sync_bank_to_db(
    db: sqlite3.Connection,
    bank_path: Path = DEFAULT_BANK_PATH,
    assets_dir: Path = CHAT_PRACTICE_DIR,
) -> dict[str, Any]:
    """
    Import validated question bank into SQLite with immutable item versions.
    If an item changes in future imports, a new version row is created while
    historical item versions remain intact so old reports never change.
    """
    items, summary = load_and_validate_bank(bank_path, assets_dir)
    now = time.time()

    existing_items = {
        row["id"]: (row["current_version"], row["content_hash"])
        for row in db.execute("SELECT id, current_version, content_hash FROM questions").fetchall()
    }

    inserted = 0
    updated = 0
    unchanged = 0

    for item in items:
        qid = item["id"]
        chash = item["content_hash"]
        facts_json = json.dumps(item["underlying_facts"], ensure_ascii=False)
        choices_json = json.dumps(item["choices"], ensure_ascii=False)
        flags_json = json.dumps(item["validation_flags"], ensure_ascii=False)

        if qid not in existing_items:
            version = 1
            db.execute(
                """
                INSERT INTO questions (
                    id, family, subject, chapter, subtopic, skill, question_type,
                    refs, stem, choices_json, answer_key, explanation, map_asset,
                    underlying_facts_json, auto_status, editorial_status,
                    validation_flags_json, current_version, content_hash, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    qid, item["family"], item["subject"], item["chapter"], item["subtopic"],
                    item["skill"], item["question_type"], item["refs"], item["stem"],
                    choices_json, item["key"], item["why"], item["map_asset"],
                    facts_json, item["auto_status"], item["editorial_status"],
                    flags_json, version, chash, now,
                ),
            )
            db.execute(
                """
                INSERT INTO question_versions (
                    question_id, version, family, subject, chapter, subtopic, skill,
                    question_type, refs, stem, choices_json, answer_key, explanation,
                    map_asset, underlying_facts_json, content_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    qid, version, item["family"], item["subject"], item["chapter"],
                    item["subtopic"], item["skill"], item["question_type"], item["refs"],
                    item["stem"], choices_json, item["key"], item["why"],
                    item["map_asset"], facts_json, chash, now,
                ),
            )
            inserted += 1
        elif existing_items[qid][1] != chash:
            version = existing_items[qid][0] + 1
            db.execute(
                """
                UPDATE questions SET
                    family=?, subject=?, chapter=?, subtopic=?, skill=?, question_type=?,
                    refs=?, stem=?, choices_json=?, answer_key=?, explanation=?, map_asset=?,
                    underlying_facts_json=?, auto_status=?, editorial_status=?,
                    validation_flags_json=?, current_version=?, content_hash=?, updated_at=?
                WHERE id=?
                """,
                (
                    item["family"], item["subject"], item["chapter"], item["subtopic"],
                    item["skill"], item["question_type"], item["refs"], item["stem"],
                    choices_json, item["key"], item["why"], item["map_asset"],
                    facts_json, item["auto_status"], item["editorial_status"],
                    flags_json, version, chash, now, qid,
                ),
            )
            db.execute(
                """
                INSERT INTO question_versions (
                    question_id, version, family, subject, chapter, subtopic, skill,
                    question_type, refs, stem, choices_json, answer_key, explanation,
                    map_asset, underlying_facts_json, content_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    qid, version, item["family"], item["subject"], item["chapter"],
                    item["subtopic"], item["skill"], item["question_type"], item["refs"],
                    item["stem"], choices_json, item["key"], item["why"],
                    item["map_asset"], facts_json, chash, now,
                ),
            )
            updated += 1
        else:
            unchanged += 1

    db.execute(
        "INSERT INTO import_audits (imported_at, total_items, auto_passed, auto_flagged, summary_json) VALUES (?, ?, ?, ?, ?)",
        (now, summary["total_imported"], summary["auto_passed"], summary["auto_flagged"], json.dumps(summary, ensure_ascii=False)),
    )
    summary["db_sync"] = {"inserted": inserted, "updated": updated, "unchanged": unchanged}
    return summary
