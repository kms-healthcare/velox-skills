# Extraction patterns by source type

## Locator schemes

| Source type | Locator format | Example |
|---|---|---|
| PDF / docx spec | `§section` or `p.N §section` | `spec-2016.pdf p.14 §4.1` |
| Slide deck | `slide N` | `kickoff.pptx slide 7` |
| Transcript | `speaker, date, hh:mm:ss` | `DBA, 2026-09-10, 00:14:30` |
| Meeting minutes | `date, item N` | `minutes-2026-09-03 item 4` |
| Ticket | `ticket-id` (+ comment N) | `JIRA-4412 comment 3` |
| Email | `date, sender, para N` | `2026-08-21, CFO, para 2` |
| Spreadsheet | `sheet!cell` | `KPI-list.xlsx Sheet1!B14` |
| Data dictionary | `sheet!row` or `table.column` | `dict.xlsx Tables!row 88` |

If a document has no page numbers or sections, add them (a numbered copy in `sources/`) before
extracting. A locator that cannot be followed in five seconds is not a locator.

---

## From a functional spec

Spec, §4.1: *"Daily revenue is the sum of all sales transactions for the day."*

```json
{ "id": "FR-01", "type": "functional",
  "title": "Daily revenue = sum of sales transactions per day",
  "statement": "Daily revenue is computed as the sum of all sales transactions for the calendar day.",
  "confidence": 0.8, "inferred": false,
  "evidence": [{ "source_id": "src-spec-2016", "source_type": "spec", "locator": "p.14 §4.1",
                 "excerpt": "Daily revenue is the sum of all sales transactions for the day.", "kind": "stated" }],
  "open_questions": ["OQ-03", "OQ-04"], "status": "extracted" }
```

Open questions this sentence *forces* (do not fill them in):
- OQ-03 grain and calendar: "Transaction date or posting date? Which timezone? When does the day close?"
- OQ-04 exclusions: "Returns? Test transactions? Internal stores?" — the spec is silent, and silence
  in a 2016 spec is not evidence of "none".

Confidence 0.8, not 1.0: the sentence is clear but a 2016 spec is tier 6.

---

## From an interview transcript

DBA, 00:14:30: *"HCM-99 isn't a store, it's the central warehouse, so we take it out of revenue.
Been that way since the 2019 reorg I think."*

Produces **two** records and one question:

```json
{ "id": "FR-07", "type": "functional",
  "title": "Exclude store code HCM-99 from revenue",
  "statement": "Transactions with store_code = 'HCM-99' (central warehouse) are excluded from revenue.",
  "confidence": 0.7, "inferred": false,
  "evidence": [{ "source_id": "src-interview-03", "source_type": "interview", "locator": "DBA, 2026-09-10, 00:14:30",
                 "excerpt": "HCM-99 isn't a store, it's the central warehouse, so we take it out of revenue.", "kind": "stated" }],
  "conflicts": [{ "source_id": "src-spec-2016", "locator": "p.14 §4.1", "note": "Spec does not mention any store exclusion" }],
  "open_questions": ["OQ-07"], "status": "extracted" }
```

```json
{ "id": "OQ-07",
  "question": "HCM-99 exclusion: still valid? Effective since the 2019 reorg? Who owns this rule?",
  "why": "Stated by the DBA from memory ('I think'); absent from the spec; affects the largest single code",
  "ask": "Head of Accounting (name: ?)", "default": "Keep as current behaviour; mark CONFLICT",
  "impact_if_wrong": "high", "blocking": ["FR-07"], "status": "open" }
```

Confidence 0.7: a named person stated it, but hedged ("I think"), and it conflicts with the spec.
The "since 2019" part is **not** a requirement — it is context for the question.

---

## From a ticket

JIRA-4412 (2024-03-02): *"Finance says revenue report double-counts split shipments. Fix: dedupe on
order_line_id before summing."* Resolution comment: *"Deployed to sp_Calc_Daily_Revenue."*

```json
{ "id": "DR-04", "type": "data",
  "title": "Revenue must be de-duplicated on order_line_id",
  "statement": "Split shipments create duplicate rows per order_line_id; revenue is computed after de-duplication on order_line_id.",
  "confidence": 0.85, "inferred": false,
  "evidence": [{ "source_id": "src-jira", "source_type": "ticket", "locator": "JIRA-4412",
                 "excerpt": "double-counts split shipments. Fix: dedupe on order_line_id before summing", "kind": "stated" }],
  "conflicts": [{ "source_id": "src-spec-2016", "locator": "p.14 §4.1", "note": "Spec predates the fix; no dedup mentioned" }],
  "open_questions": [], "status": "extracted" }
```

Tickets are the best source for *why*. Note the implied **grain** (order line) — that is an
inferred requirement of its own if no source states the grain:

```json
{ "id": "DR-05", "type": "data", "title": "Revenue fact grain is order line",
  "confidence": 0.6, "inferred": true,
  "evidence": [{ "source_id": "src-jira", "locator": "JIRA-4412", "excerpt": "dedupe on order_line_id — implies the fact is at order-line grain", "kind": "inferred" }],
  "open_questions": ["OQ-09"], "status": "extracted" }
```

Every `inferred` record has a question. No exceptions.

---

## From a deck

Kickoff, slide 7: *"Goal: real-time revenue dashboard for store managers."*

Do **not** create `NFR: latency < 1 minute`. Create:

```json
{ "id": "NFR-02", "type": "nonfunctional",
  "title": "Revenue dashboard freshness for store managers — tier TBD",
  "statement": "Store managers need a revenue dashboard; the stated wish is 'real-time'. Required freshness tier not yet established.",
  "confidence": 0.5, "inferred": false,
  "evidence": [{ "source_id": "src-kickoff", "source_type": "deck", "locator": "slide 7", "excerpt": "real-time revenue dashboard for store managers", "kind": "stated" }],
  "open_questions": ["OQ-12"], "status": "extracted" }
```

OQ-12: *"What does a store manager do within 5 minutes of a sale that they cannot do with data as
of 15 minutes ago? If nothing, the tier is micro-batch or daily."* — `impact_if_wrong: high`,
because "real-time" is the single most expensive word in a Databricks requirement.

---

## From a data dictionary

Dictionary row: `STG_POS_TXN.STORE_CD — Store code, FK to DIM_STORE`.

This is **not** a requirement. It is a name mapping. Use it to read other sources accurately, and
to seed `inventory_tables.jsonl` *if* the dictionary is trusted (check its date against the DDL).
Do not create requirements from a dictionary alone.

---

## What a finished review.md says for a document run

- Documents read, in tier order, with dates.
- Count by type; confidence histogram.
- Top-5 conflicts and who can settle each.
- The **absent requirements** list (grain, exclusions, history, restatement, deadline, tolerance,
  consumers, access) — each as an open question, none invented.
- "Deliberately not concluded": everything about the *running* system, because documents cannot
  tell you that.
