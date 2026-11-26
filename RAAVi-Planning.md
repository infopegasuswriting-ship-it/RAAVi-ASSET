# RAAVi — Your Personal Examiner

Standalone assessment planning for Pakistan Studies (PST) by Khizar Hayat.

## Workbook audit

Workspace write access was verified by creating, reading, and removing a temporary file. Both source PDFs were found in `C:\Users\lenovo\Downloads`. The audit scanned the text layer on all 333 pages and visually sampled both workbooks. Page references below are 1-based PDF page numbers. Item counts require editorial review after segmentation.

| Source | Coverage | Import implications |
| --- | --- | --- |
| History Workbook by KH.pdf, *Echoes of the Past* | 221 pages and 16 numbered chapters. Page 2 is introductory and pages 1 and 221 are artwork. | Distinguish short recall, explanation, extended evaluation, written-source and picture-source questions. Page 8 has alternate phrasings and a shared trailing mark label under a mixed 14/10 heading. Pages 8–9 contain continued answer scaffolding. Page 10 reuses “Source A” for different passages. Pages 11 and 31 tie “Source B” to different images. Page 61 mixes a timeline with possible questions. |
| Geography Workbook by KH.pdf, *Discovering Pakistan* | 112 pages. Maps and physical geography precede numbered Units 02–12. Past-paper material appears near the end. | Page 2 contains both study guidance and an assessable map exercise. Pages 2–3 require precise map label placement. Pages 8 and 10 contain answer grids. Page 23 requires paired climate graphs. Page 31 combines definitions, a canal diagram and a comparison grid. Pages 109–112 include past-paper references, figures and nested subparts. |

History's text contains 329 line-leading `Q.` markers and Geography contains 112. These are parser diagnostics. Alternate stems, implicit prompts, multipart exercises, and marks printed inside instructions make these counts unsuitable for inventory totals. History has eight pages with explicit “Mark Scheme” headings. Their contents provide topic cues and response structure, with full scoring criteria still requiring a source or reviewer approval. Geography's text scan found no “Mark Scheme,” “Answer Key,” or “Model Answer” heading. Individual item completeness remains to be verified.

| Source | SHA-256 |
| --- | --- |
| History | `343D0765862948A742445FF9132A3F94ABEB50A7A722601F80052CB436F40D7F` |
| Geography | `3A1E094CCAE4D4E2443D3E8F462101F784B47BC010B7161D4FC75457DDCA946A` |

## Structured import

1. Register each PDF by filename, checksum, edition and page count. Save page text with coordinates and classify regions as prompt, stimulus, marks, guidance, answer area, reference material or page decoration. Use targeted OCR only if a relevant image region lacks usable text. Retain the source text alongside reviewed display text so encoding and line-break repairs can be traced.
2. Parse History by chapter and question block. Carry continuation material across pages, preserve alternatives as a group and scope source labels to their local passage or image. Parse Geography by unit, worksheet exercise, past-paper block and nested part. Distinguish grid headers and blank response cells from factual tables. Keep original label order, units, graph legends and page regions. Capture cited exam session and question number where printed.
3. Stage records with stable item IDs and immutable revisions. Store subject, topic, command word, item type, parent and part order, alternative group, prompt, response format, maximum marks and where they were found, optional guidance, stimulus IDs, and page regions. Store each stimulus separately with its label, text or asset, source coordinates, reading order and accessible equivalent. Verify figures at assessment display size and ensure accessibility descriptions preserve the task without supplying its answer. Keep rubric revisions, accepted responses, partial-credit rules and approval status separate from workbook guidance.
4. Pilot the layouts listed above before bulk extraction. Review missing or conflicting marks, uncertain boundaries, variable exam references, stray encoding, omitted illustrations, repeated prompts and visually ambiguous tables. Keep a page ledger linking every region to staged records, a review flag or an exclusion reason. Confirm reuse clearance for exam extracts and third-party images before publishing them. Stage incomplete records for review and require approved scoring criteria, marks, stimuli and provenance before a record enters a scored assessment.
5. Reconcile counts after review by subject, chapter or unit, item type and status. Check every published item against the source and every multipart total against its parts where a total is printed. Re-running the same source checksum and import build must produce the same candidate identifiers. Corrections create revisions, and prior attempts retain the exact published revisions they used.

## Standalone product plan

- **Signup and email verification.** Store a stable learner ID, normalized email with uniqueness enforcement, verification timestamp and account status. Send a single-use, expiring verification link. Rate-limit sends and allow retries. Require verification before starting an assessment. Keep email private and scope attempts and reports to their owner.
- **Two starts per rolling 24 hours.** Use server UTC and a per-learner transaction to count committed starts in the preceding 24 hours and allocate a slot atomically. Count a start when its attempt and assigned form are committed, including attempts later abandoned. Resume uses the same attempt. A failed allocation leaves no start. A repeated request with the same idempotency key returns its existing attempt. When both slots are occupied, show the earliest active start plus 24 hours as the next eligible time.
- **Saved reports.** Persist the served item and rubric revisions, responses, award and maximum per item, feedback, total, timestamps and assessment blueprint. Make submission and grading retries idempotent. Expose pending reports during grading and retain published reports as versioned snapshots so learners can reopen them after question or rubric updates.
- **Comparable progress.** Use versioned form blueprints with fixed subject, topic and skill coverage, mark mix and calibrated difficulty where available. Plot earned marks as a share of available marks for finalized attempts within the same comparison series, and show the marks and number of attempts behind the trend. Start a separate series after a material change to form or scoring unless equivalence has been established. Use repeated or reviewed anchor items to evaluate comparability of different forms before combining them.
- **Later website integration.** Give RAAVi its own deployment, routes, learner records, question bank and report storage. Keep account, assessment and reporting interfaces independent of the future website. Start with a link into RAAVi as the proposed integration. Consider federated sign-in later through stable learner ID mapping so reports and quota history follow the same learner.

## Readiness checks

The import pilot passes when a reviewer can reconstruct each selected prompt, mark allocation, subpart and stimulus from its source regions and independently verify its rubric. The product acceptance cases cover unverified access, simultaneous starts with one slot left, repeated start requests, resumption and abandonment, and eligibility at the 24-hour boundary. Report checks cover ownership, repeat submission, reopening after question edits and combining only equivalent assessment attempts in a progress series.

Before implementation, confirm the first assessment blueprint, who approves scoring rubrics, and which workbook figures and exam extracts can be used in the published bank. The audit and plan precede item ingestion and application development.

## Long-answer marking and live practice

In practice, the learner chooses **Check draft** after writing a passage. Return one observation tied to their words and one question that helps them develop their reasoning. On **Submit**, freeze the answer and assess the whole response. Record whether the learner used coaching. Use first, unaided submissions for exam-mode trends and give coached revisions their own practice history. In exam mode, save drafts silently and release feedback after submission.

For the planned OpenAI API integration, RAAVi's server submits the question, any required source or figure, the approved item-specific rubric, benchmark examples and the frozen answer. Omit the learner's email. Treat the answer as quoted student work. Ask the model to identify credited evidence, match the rubric descriptor and justify the mark, accepting valid alternative arguments. Apply the rubric's own level or point rules. Credit a repeated idea once and assess writing mechanics only where the rubric calls for them.

Validate the returned item and rubric IDs, score bounds and exact evidence quotes before saving. Show a marking-in-progress status while waiting. Retry a failed grading job against the same submission. Missing stimuli, unverifiable quotes or unresolved scoring disagreements go to a reviewer, with a pending report until resolved. Save model, prompt and rubric versions with the final report.

Before enabling automatic marks, have Khizar or a designated examiner independently score a held-out set spanning weak, borderline and strong answers. Include fluent but inaccurate responses, terse accurate ones and alternative interpretations. Compare AI and examiner marks by item type and level, measure exact and within-one-mark agreement, and inspect systematic over- or under-marking. Agree release thresholds with the examiner, repeat the checks after model or rubric changes, and retain reviewed corrections as report revisions.

### Chat rehearsal

Use the seven-mark History prompt on the causes of the 1857 uprising (page 36). For this demonstration only, use a provisional scale of up to two marks for each of three distinct causes (one for accurate identification and one for explaining how it encouraged resistance), plus one for a specific, accurate detail that strengthens a causal link. A learner may send a draft for coaching or submit directly for a mark. Return the total, short quotations showing what earned credit, the reason for any missing marks and one targeted improvement. This exercise tests the feedback experience. API timing, production grading reliability and agreement with an examiner require separate measurement.
