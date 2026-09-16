---
name: requirements-extraction
description: >
  Use when documents for a data, lakehouse, migration or analytics project have to become
  requirements — specs, decks, meeting minutes, interview transcripts, tickets, emails, RFPs, data
  dictionaries. Triggers: "extract requirements", "what does this spec actually ask for", "build
  the requirements register", "find what the documents contradict", "turn these interview notes
  into requirements", a folder of client documents handed over, or a project brief that has to be
  split into functional, data, security, non-functional, scope and integration requirements. Not
  for reading source code (use legacy-etl-archaeology) or writing the report (assessment-synthesis).
compatibility: Runs outside Databricks. Filesystem only.
metadata:
  version: "0.3.0"
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

## The Iron Law

```
NO REQUIREMENT WITHOUT A LOCATOR.
NO INFERENCE WITHOUT AN OPEN QUESTION.
```

**Violating the letter of these rules is violating the spirit of these rules.** A requirement whose
evidence is another requirement has no locator.

## Red Flags — stop and re-read the source

- A requirement marked `stated` that you assembled from two sentences in different places
- An `inferred` requirement with no entry in `open_questions`
- A `conflicts[]` you resolved by judging which source was newer, more senior, or more sensible
- `priority` or `owner` filled in when no source states them — or an `owner` that is a department
- Code, or `business_rules.jsonl`, in context while you are reading documents
- Writing into `registers/` instead of `runs/<run>/`
- About to read all thirty documents before delivering anything

**Every one of these means: go back to the document and quote it, or raise a question instead.**

## Rationalizations

| Excuse | Reality |
|---|---|
| "The spec obviously implies this — I'll record it as stated" | Obvious to you is `inferred`. Label it, give the basis, raise the question. That is the whole difference between a register and a narrative. |
| "The doc says 5,000 and the interview says 10,000; the interview is newer, so it wins" | Record both in `conflicts[]` and one question with a named `ask`. Picking a side quietly is how a wrong number reaches production with a citation. |
| "The engineer in this chat confirmed it, so the conflict is closed" | `user-relayed` raises confidence. Only the owner named in `ask`, with a locator, resolves it. |
| "Reading the stored procedures alongside will help me interpret the spec" | It produces a seamless document — seamless exactly where the system drifted. Extract, then diff. |
| "Finance owns this requirement" | A department cannot answer a question. A role with a name, or `(name: ?)`. |
| "Thirty documents — I'll read them all, then deliver one complete register" | Deliver batch by batch. A partial register a human can merge beats a complete one that lands after the budget. |
| "This wiki page is detailed and confident, I'll treat it as a source" | AI-generated or draft pages are hypotheses. Verify every identifier somewhere else first. |
| "Nobody stated the grain, so I'll use the obvious one" | Grain is never written down and is the single most expensive thing to get wrong. It is a question, not a value. |

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

## Working in a chat

`../discovery-intake/references/interaction-protocol.md` binds here. Two things matter most in this
skill:

- **Every reply has four parts** — what I concluded · what I wrote (paths) · ≤ 5 blocking questions
  · what I deliberately did not conclude. The register is the deliverable; restating it in chat is
  a third copy with no locator.
- **An answer given in this chat is `user-relayed`, not `client-confirmed`.** The engineer saying
  "yes, that is what Finance means" raises confidence and keeps the question open against the named
  owner; it never resolves a `conflicts[]` entry and never confirms an `inferred` requirement. Only
  the owner in `ask`, with a locator, does that.

Before thirty documents, say the batch plan in one line and deliver batch by batch. Checkpoint when
a document turns out to be something other than its title, or when an assumption would change the
reading of everything already done.

## Output and calibration

`runs/<run>/`: `requirements.jsonl`, `findings.jsonl`, `open_questions.jsonl`, `manifest.json`,
`review.md` (what a human must decide now · confidence distribution · **deliberately not
concluded**). Never write into `registers/`.

Before thirty documents, do one the client knows well and have them correct the register. The
correction rate is this project's error rate; fix the method (locator scheme, granularity) before
scaling.

## References

`../discovery-intake/references/run-layout.md` (required) ·
`../discovery-intake/references/interaction-protocol.md` (required) · `references/extraction-patterns.md`
— worked examples per source type (spec, transcript, ticket, deck, dictionary) with locator formats.
