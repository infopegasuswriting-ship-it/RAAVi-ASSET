# RAAVi Question Bank Validation & Inventory Report

- **Total cards imported:** 5600
- **Passed automated validation:** 5600
- **Flagged by automated validation:** 0
- **Source family ID collisions detected:** 2

## Subject Composition

| Subject | Standalone | Timeline (Event Ordering) | Matching | Total | Unique Families |
|---|---:|---:|---:|---:|---:|
| History | 411 | 273 | 2516 | 3200 | 3199 |
| Geography | 265 | 0 | 2135 | 2400 | 2399 |

## Automated Checks & Editorial Review Separation

- **Automated validation (`auto_status = passed`):** Verifies schema completeness, 4 distinct choices, valid answer key, non-empty explanation, valid source codes/pages, valid map asset paths (`city-pins.png`, `barrage-pins.png`), and matching topic-to-chapter mapping.
- **Editorial / subject-accuracy review (`editorial_status`):** Kept separate from automated validation. `KH-*` items (228) are authored prompts still marked `authored_uncalibrated` until student response data supports difficulty calibration; generated `R-*`, `timeline-*`, and `matching-*` items (5,372) are marked `pending_editorial_review`.
- **Anomalies detected in source files:**
  - Duplicate source ID `KH-001` appears 2 times in `chat-practice/questions.txt` (both prompts are distinct valid items; importer preserves source family `KH-001` and assigns disambiguated item ID `KH-001#2` to the second row).
  - Duplicate source ID `KH-126` appears 2 times in `chat-practice/questions.txt` (both prompts are distinct valid items; importer preserves source family `KH-126` and assigns disambiguated item ID `KH-126#2` to the second row).
  - On `chat-practice/city-pins.png` (`M:3`), letters `R` (Rawalpindi, Rahim Yar Khan) and `S` (Swat, Sialkot) each appear twice on the figure; the 9 active map-pin items (`KH-142`..`KH-150`) only target unambiguous single-letter pins (`G, Q, H, L, P, M, I, J, K`).
  - Legacy `bank.py` contains 30 prototype MCQs (15 History, 15 Geography) with no source page references; they are excluded from the verified bank pending source citations.

## Chapter-by-Chapter Inventory

| # | Subject | Chapter | Total | Auto Passed | Unique Families | Standalone | Timeline | Matching | Map Pin | Editorial Status |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | History | Mughal decline and British expansion | 200 | 200 | 199 | 28 | 10 | 162 | 0 | authored_uncalibrated: 10, pending_editorial_review: 190 |
| 2 | History | Religious thinkers | 200 | 200 | 200 | 25 | 30 | 145 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 3 | History | Uprising of 1857 | 200 | 200 | 200 | 25 | 10 | 165 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 4 | History | Sir Syed Ahmad Khan | 200 | 200 | 200 | 25 | 20 | 155 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 5 | History | Urdu and regional languages | 200 | 200 | 200 | 25 | 0 | 175 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 6 | History | Early Pakistan Movement | 200 | 200 | 200 | 25 | 10 | 165 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 7 | History | Khilafat Movement | 200 | 200 | 200 | 25 | 12 | 163 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 8 | History | Pakistan Movement, 1927–39 | 200 | 200 | 200 | 25 | 35 | 140 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 9 | History | Negotiations and partition, 1940–47 | 200 | 200 | 200 | 25 | 10 | 165 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 10 | History | Jinnah, Iqbal and Rahmat Ali | 200 | 200 | 200 | 25 | 10 | 165 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 11 | History | Establishing Pakistan | 200 | 200 | 200 | 25 | 0 | 175 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 12 | History | Stability and government after Jinnah | 200 | 200 | 200 | 25 | 10 | 165 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 13 | History | Creation of Bangladesh | 200 | 200 | 200 | 25 | 1 | 174 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 14 | History | Bhutto and Zia | 200 | 200 | 200 | 25 | 35 | 140 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 15 | History | Governments, 1988–99 | 200 | 200 | 200 | 25 | 30 | 145 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 16 | History | International relations | 200 | 200 | 200 | 33 | 50 | 117 | 0 | authored_uncalibrated: 15, pending_editorial_review: 185 |
| 1 | Geography | Topography | 200 | 200 | 200 | 32 | 0 | 168 | 9 | authored_uncalibrated: 17, pending_editorial_review: 183 |
| 2 | Geography | Climate | 200 | 200 | 200 | 20 | 0 | 180 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 3 | Geography | Water resources | 200 | 200 | 200 | 25 | 0 | 175 | 3 | authored_uncalibrated: 11, pending_editorial_review: 189 |
| 4 | Geography | Forests | 200 | 200 | 200 | 21 | 0 | 179 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 5 | Geography | Minerals | 200 | 200 | 200 | 19 | 0 | 181 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 6 | Geography | Fishing | 200 | 200 | 200 | 21 | 0 | 179 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 7 | Geography | Agriculture | 200 | 200 | 200 | 21 | 0 | 179 | 0 | authored_uncalibrated: 8, pending_editorial_review: 192 |
| 8 | Geography | Power | 200 | 200 | 200 | 20 | 0 | 180 | 0 | authored_uncalibrated: 7, pending_editorial_review: 193 |
| 9 | Geography | Industry | 200 | 200 | 200 | 22 | 0 | 178 | 0 | authored_uncalibrated: 8, pending_editorial_review: 192 |
| 10 | Geography | Trade | 200 | 200 | 200 | 22 | 0 | 178 | 0 | authored_uncalibrated: 9, pending_editorial_review: 191 |
| 11 | Geography | Transport and telecommunications | 200 | 200 | 199 | 20 | 0 | 180 | 0 | authored_uncalibrated: 8, pending_editorial_review: 192 |
| 12 | Geography | Population and employment | 200 | 200 | 200 | 22 | 0 | 178 | 0 | authored_uncalibrated: 9, pending_editorial_review: 191 |
