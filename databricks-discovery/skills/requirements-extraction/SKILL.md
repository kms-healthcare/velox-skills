---
name: requirements-extraction
description: >
  Turn raw project inputs — specs, decks, meeting minutes, interview transcripts, tickets, emails,
  RFPs, data dictionaries — into a traceable requirements register for a Databricks data project:
  every requirement with type, source locator, stated-vs-inferred label, confidence, conflicts
  between sources, and the open questions it raises. Use after discovery-intake has classified the
  project, whenever the user has documents to read for a data / lakehouse / migration / analytics
  project and asks to "extract requirements", "what does this spec actually ask for", "build the
  requirements register", "find what the documents contradict", "turn these interview notes into
  requirements", or hands over a folder of client documents. Also use when a Databricks project
  brief needs to be decomposed into functional, data, security, non-functional, scope and
  integration requirements. Not for reading source code (use legacy-etl-archaeology) and not for
  writing the final report (use assessment-synthesis).
compatibility: Runs outside Databricks. Filesystem only.
metadata:
  version: "0.2.0"
parent: discovery-intake
---

# Requirements extraction — documents in, register out

A narrative requirements document fails in a specific way: it is fluent, and nobody can tell which
sentence came from the 2016 spec, which from the DBA, and which the model filled in. This skill
produces a **register** instead — one record per requirement with locator, `stated`/`inferred`,
confidence, conflicts, and the question it leaves open. Schemas and the record budget:
`../discovery-intake/references/run-layout.md`. Read it first. Rules 1–3 of `discovery-intake`
apply.

Inputs: `intake.md` (the decision to serve — without it you get 200 rows and no priorities) and
the source list. Register each source in `manifest.json` (path, sha256) **before** reading. Do not
copy files.

## Reading order — reliability about actual behaviour, high to low

1. UAT scripts, test plans, acceptance sheets (literal input/output — rarely offered, always ask)
2. Runbooks, user manuals, training decks
3. Tickets, change requests, incidents — the only record of *why* something changed
4. Interview transcripts, minutes — attribute to person + timestamp
5. Design documents · 6. Requirements docs / RFPs — intent, not behaviour
7. AI-generated or draft wiki pages — **hypothesis only**; verify every identifier elsewhere

Glossaries and data dictionaries may be read first: they map names, not behaviour. If
`legacy-etl-archaeology` is also running, **do not load its code-derived rules while reading
documents** — extract, then diff. Both in context smooths over exactly the disagreements that matter.

## Procedure

Per source: skim for structure and choose the locator scheme → extract **atomic, testable**
statements (split "and") → `type` ∈ functional | data | security | nonfunctional | scope |
integration → evidence with `kind` (`inferred` **always** raises an open question) → `confidence`
→ `priority` and `owner` only when the source states them (departments are not owners).

Across sources of the same tier: merge duplicates (two evidence entries, higher confidence);
**record conflicts, never pick a side** — doc says 5,000, interview says 10,000 → both in
`conflicts[]`, one question with `ask` set to who can settle it; write `findings` for what is not
a requirement but matters (stale source, missing stakeholder, stated assumption contradicted).

`target_mapping.layer` may follow the requirement's nature (ingestion → bronze; conformance,
history, quality → silver; metrics, access → gold). `target_mapping.object` stays a placeholder.
Metric definitions: record measure and dimensions separately — they belong in Unity Catalog metric
views.

## Requirements that are never written down — look for their absence

Create an open question, never a value, for each one no source states:

| Missing | Why always missing | Question |
|---|---|---|
| Grain | people think in reports, not rows | "One row here is one what?" |
| Exclusions (test, intercompany, cancelled) | applied silently today | "Which records do you deliberately leave out?" |
| History depth / point-in-time semantics | assumed "whatever exists" | "When an attribute changes, do old reports change?" |
| Restatement | nobody thinks of it before month 2 | "Do last month's numbers ever get corrected?" |
| Deadline vs latency | both written as "daily" | "Ready by what time, which timezone?" |
| Tolerance | assumed zero | "If this is 2% off, what happens?" |
| Consumers beyond the named report | Excel, ODBC, downstream apps | "Who complains when it is late?" |
| Access model | found after Gold exists | "Who must *not* see this?" |
| Definitions in conflict across departments | each assumes theirs | measure the gap when data exists; ask which is official |

## Output and calibration

`runs/<run>/`: `requirements.jsonl`, `findings.jsonl`, `open_questions.jsonl`, `manifest.json`,
`review.md` (what a human must decide now · confidence distribution · **deliberately not
concluded**). Never write into `registers/`.

Before thirty documents, do one the client knows well and have them correct the register. The
correction rate is this project's error rate; fix the method (locator scheme, granularity) before
scaling.

## References

`../discovery-intake/references/run-layout.md` (required) · `references/extraction-patterns.md`
— worked examples per source type (spec, transcript, ticket, deck, dictionary) with locator formats.
