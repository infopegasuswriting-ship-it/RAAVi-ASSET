# RAAVi Chapter Practice Capacity Simulation Report

Simulation uses the live `select_questions_from_pool` selector with:
- **10 questions per test** from one selected chapter
- **62-day per-student family lockout**
- **At most 2 matching items per 10-question test** (requiring at least 8 non-matching items per test)
- **Zero duplicate underlying facts within any single 10-question test**

## Key Findings

- **Can the current bank promise 6 months (184 days) of fresh same-chapter practice?** **No.**
- **Minimum same-chapter capacity:** 2 day(s) (Religious thinkers).
- **Maximum same-chapter capacity:** 3 day(s) (Mughal decline and British expansion).
- **Rotating-chapter student (History, 16 chapters):** Sustained **33 consecutive daily tests** before first shortage on day 34 in `Religious thinkers`.
- **Rotating-chapter student (Geography, 12 chapters):** Sustained **25 consecutive daily tests** before first shortage on day 26 in `Climate`.

Why same-chapter capacity is constrained even though each chapter has 200 cards:
1. With at most 2 matching items per 10-question test, each test requires at least **8 non-matching items** (`standalone + timeline`). Most Geography chapters have only 19–25 standalone items and 0 timeline items, capping them at **2–3 tests** before running out of non-matching items.
2. Even when timeline or standalone counts are higher, `timeline` and `matching` items combine underlying `R-*` recall facts. Requiring zero repeated facts inside a single test prevents combining cards that share the same underlying facts.
3. Sustaining 62 days of daily same-chapter tests requires at least **496 non-matching unique-fact items** (62 × 8) and 620 total eligible non-overlapping families per chapter; 184 days requires at least **1,472 non-matching items** and 1,840 eligible families per chapter.

## Same-Chapter Daily Practice Capacity (184-Day Test)

| # | Subject | Chapter | Non-Matching (Standalone + Timeline) | Matching | Complete Daily Tests Sustained | Meets 62d? | Meets 184d? |
|---:|---|---|---:|---:|---:|---|---|
| 1 | History | Mughal decline and British expansion | 38 (28+10) | 162 | 3 | No | No |
| 2 | History | Religious thinkers | 55 (25+30) | 145 | 2 | No | No |
| 3 | History | Uprising of 1857 | 35 (25+10) | 165 | 2 | No | No |
| 4 | History | Sir Syed Ahmad Khan | 45 (25+20) | 155 | 2 | No | No |
| 5 | History | Urdu and regional languages | 25 (25+0) | 175 | 2 | No | No |
| 6 | History | Early Pakistan Movement | 35 (25+10) | 165 | 2 | No | No |
| 7 | History | Khilafat Movement | 37 (25+12) | 163 | 2 | No | No |
| 8 | History | Pakistan Movement, 1927–39 | 60 (25+35) | 140 | 2 | No | No |
| 9 | History | Negotiations and partition, 1940–47 | 35 (25+10) | 165 | 2 | No | No |
| 10 | History | Jinnah, Iqbal and Rahmat Ali | 35 (25+10) | 165 | 2 | No | No |
| 11 | History | Establishing Pakistan | 25 (25+0) | 175 | 2 | No | No |
| 12 | History | Stability and government after Jinnah | 35 (25+10) | 165 | 2 | No | No |
| 13 | History | Creation of Bangladesh | 26 (25+1) | 174 | 2 | No | No |
| 14 | History | Bhutto and Zia | 60 (25+35) | 140 | 2 | No | No |
| 15 | History | Governments, 1988–99 | 55 (25+30) | 145 | 2 | No | No |
| 16 | History | International relations | 83 (33+50) | 117 | 3 | No | No |
| 1 | Geography | Topography | 32 (32+0) | 168 | 3 | No | No |
| 2 | Geography | Climate | 20 (20+0) | 180 | 2 | No | No |
| 3 | Geography | Water resources | 25 (25+0) | 175 | 2 | No | No |
| 4 | Geography | Forests | 21 (21+0) | 179 | 2 | No | No |
| 5 | Geography | Minerals | 19 (19+0) | 181 | 2 | No | No |
| 6 | Geography | Fishing | 21 (21+0) | 179 | 2 | No | No |
| 7 | Geography | Agriculture | 21 (21+0) | 179 | 2 | No | No |
| 8 | Geography | Power | 20 (20+0) | 180 | 2 | No | No |
| 9 | Geography | Industry | 22 (22+0) | 178 | 2 | No | No |
| 10 | Geography | Trade | 22 (22+0) | 178 | 2 | No | No |
| 11 | Geography | Transport and telecommunications | 20 (20+0) | 180 | 2 | No | No |
| 12 | Geography | Population and employment | 22 (22+0) | 178 | 2 | No | No |

## Priority Chapters for New Question Writing

Ranked by lowest same-chapter capacity first:

- **Geography · Minerals**: sustains **2** test(s) (19 standalone, 0 timeline).
- **Geography · Climate**: sustains **2** test(s) (20 standalone, 0 timeline).
- **Geography · Power**: sustains **2** test(s) (20 standalone, 0 timeline).
- **Geography · Transport and telecommunications**: sustains **2** test(s) (20 standalone, 0 timeline).
- **Geography · Forests**: sustains **2** test(s) (21 standalone, 0 timeline).
- **Geography · Fishing**: sustains **2** test(s) (21 standalone, 0 timeline).
- **Geography · Agriculture**: sustains **2** test(s) (21 standalone, 0 timeline).
- **Geography · Industry**: sustains **2** test(s) (22 standalone, 0 timeline).
- **Geography · Trade**: sustains **2** test(s) (22 standalone, 0 timeline).
- **Geography · Population and employment**: sustains **2** test(s) (22 standalone, 0 timeline).
- **History · Urdu and regional languages**: sustains **2** test(s) (25 standalone, 0 timeline).
- **History · Establishing Pakistan**: sustains **2** test(s) (25 standalone, 0 timeline).
- **Geography · Water resources**: sustains **2** test(s) (25 standalone, 0 timeline).
- **History · Creation of Bangladesh**: sustains **2** test(s) (25 standalone, 1 timeline).
- **History · Uprising of 1857**: sustains **2** test(s) (25 standalone, 10 timeline).
- **History · Early Pakistan Movement**: sustains **2** test(s) (25 standalone, 10 timeline).
- **History · Negotiations and partition, 1940–47**: sustains **2** test(s) (25 standalone, 10 timeline).
- **History · Jinnah, Iqbal and Rahmat Ali**: sustains **2** test(s) (25 standalone, 10 timeline).
- **History · Stability and government after Jinnah**: sustains **2** test(s) (25 standalone, 10 timeline).
- **History · Khilafat Movement**: sustains **2** test(s) (25 standalone, 12 timeline).
- **History · Sir Syed Ahmad Khan**: sustains **2** test(s) (25 standalone, 20 timeline).
- **History · Religious thinkers**: sustains **2** test(s) (25 standalone, 30 timeline).
- **History · Governments, 1988–99**: sustains **2** test(s) (25 standalone, 30 timeline).
- **History · Pakistan Movement, 1927–39**: sustains **2** test(s) (25 standalone, 35 timeline).
- **History · Bhutto and Zia**: sustains **2** test(s) (25 standalone, 35 timeline).
- **Geography · Topography**: sustains **3** test(s) (32 standalone, 0 timeline).
- **History · Mughal decline and British expansion**: sustains **3** test(s) (28 standalone, 10 timeline).
- **History · International relations**: sustains **3** test(s) (33 standalone, 50 timeline).
