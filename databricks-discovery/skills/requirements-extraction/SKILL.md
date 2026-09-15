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
compatibility: Runs outside Databricks. Filesystem only; no network required.
metadata:
  version: "0.1.0"
parent: discovery-intake
---

# Requirements extraction — documents in, register out

## What this skill produces, and why not a narrative

The naive approach — read everything, write a requirements document — fails in a specific way:
the output is fluent and internally consistent, and nobody can tell which sentences came from the
2016 spec, which from the DBA interview, and which the model filled in. On a data project that
means a Gold table gets built on a rule nobody asked for.

This skill produces a **register**: one record per requirement, each carrying where it came from
(`locator`), whether the source said it or the agent inferred it, how confident the agent is, what
other sources disagree, and what question it leaves open. Reviewable by a human, splittable across
people, honest about what is not known. Schemas are in
`../discovery-intake/references/run-layout.md` — read it before writing a single record.

## Inputs this skill expects

From `discovery-intake`: `intake.md` (project type and the decision to serve) and the list of
sources with `source_id`s. If intake has not run, run it first — extracting requirements without
knowing the decision they serve produces a register with 200 rows and no priorities.

Register every source in `manifest.json` with `source_id`, path and sha256 **before** reading it.
Do not copy files that already exist on disk into `sources/` — reference them by path; only
originals that may move (email bodies, chat exports) get a copy. Copying thirty files costs
minutes and proves nothing.

## Reading order — and why it matters

**Tier documents by how reliable they are about actual behaviour**, then read most-reliable first
so that later, weaker documents are diffed against stronger ones rather than the reverse:

1. **UAT scripts, test plans, acceptance sheets** — literal input/output pairs. Rarely provided,
   always ask.
2. **Operational runbooks, user manuals, training decks** — describe what people actually do.
3. **Tickets, change requests, incident reports** — the only place that records *why* something
   changed. Read the last 2–3 years.
4. **Interview transcripts and meeting minutes** — current intent; attribute every statement to a
   named person and timestamp.
5. **Design documents** — the system as intended at some date.
6. **Requirements documents and RFPs** — written before anything existed; least reliable about
   behaviour, most reliable about original intent.
7. **AI-generated documentation, wiki pages marked draft** — *tier zero: hypothesis only.* Use for
   orientation; verify every identifier and number elsewhere before it enters the register.

**Glossaries and data dictionaries may be read first** — they map names, not behaviour, and make
everything downstream more accurate.

If `legacy-etl-archaeology` is also in play: **do not load its code-derived rules while reading
documents.** Extract from documents alone, then diff. Same reason as code-first over there: with
both in context the model smooths over exactly the disagreements that matter.

## Extraction procedure

Work one source at a time. For each source:

1. **Skim for structure**, note sections and the locator scheme you will use (`page:section`,
   `slide N`, `hh:mm:ss`, `ticket-id`).
2. **Extract candidate requirements** — one record per atomic, testable statement. "The platform
   must be secure" is not a requirement; "CCCD and phone must be masked for all groups except
   Customer Care" is. Split compound sentences.
3. **Classify `type`**: `functional | data | security | nonfunctional | scope | integration`.
   `data` covers grain, history, quality, retention, lineage; `scope` covers what is explicitly in
   or out; `integration` covers systems that must connect.
4. **Attach evidence** with `kind`:
   - `stated` — the source says it; `excerpt` quotes it (≤ 200 chars), `locator` points at it.
   - `inferred` — you derived it (e.g. a 07:00 report deadline implies a data SLA before 06:30);
     record the basis in `excerpt`, and **create an open question** — every inference needs a
     confirmer.
5. **Set `confidence`** (0–1): how sure you are the record reflects what the source means. Use it to
   order review, never to skip it.
6. **Leave `priority` null** unless the source states it. Priorities come from the sponsor in
   `assessment-synthesis`, not from the document's tone.
7. **`owner` is null** unless a named person is given. Departments are not owners.

Then, after all sources of the same tier are done, **cross-source diff**:

8. **Merge duplicates** — same requirement from two sources → one record, two evidence entries.
   Agreement raises confidence.
9. **Record conflicts** — two sources disagree → one record, `conflicts[]` filled, and an
   `open_question` with `ask` set to whoever can settle it. **Never pick a side.** Document says
   5,000, interview says 10,000: record both; the answer is a business decision.
10. **Write `findings`** for anything that is not a requirement but matters: a stated assumption
    that contradicts evidence, a source that is out of date, a stakeholder who is missing.

## Requirements that are never in the documents — look for their absence

Data projects fail on requirements nobody wrote down. For each of these, if no source states it,
create an `open_question` rather than inventing a value:

| Missing requirement | Why it is always missing | Question to raise |
|---|---|---|
| **Grain** of each reporting object | Business people think in reports, not rows | "One row in this report is one what?" |
| **Exclusions** (test orders, intercompany, cancelled, internal accounts) | Applied silently in today's report | "Which records do you deliberately leave out today?" |
| **History depth and point-in-time semantics** | Assumed to be "whatever the system has" | "When an attribute changes, do old reports change?" |
| **Restatement** — can published numbers change, how far back | Nobody thinks about it until month 2 | "Do last month's numbers ever get corrected?" |
| **Freshness as a deadline** ("before 07:00") vs latency ("within 1 h") | Both get written as "daily" | "By what time must it be ready, in which timezone?" |
| **Tolerance** — how wrong is acceptable | Assumed zero, never true | "If this is off by 2%, what happens?" |
| **Consumers** beyond the named report | Excel, Access, downstream systems | "Who complains when it is late?" |
| **Access model** — who may see which columns | Discovered after Gold is built | "Who is *not* allowed to see this?" |
| **Definitions in conflict** between departments | Each department assumes theirs is the one | Measure the gap when data is available; ask which is official |

## Mapping to the target — only when the evidence supports it

`target_mapping.layer` (`bronze | silver | gold`) may be set from the requirement's nature:
ingestion/retention → bronze; conformance, dedup, history, quality → silver; metrics, aggregates,
access views → gold. `target_mapping.object` stays a **placeholder** (`<catalog>.silver.<entity>`)
until a name is verified in Unity Catalog. Never write a name that looks real.

Metric definitions are a special case: they should ultimately land in **Unity Catalog metric
views**, so record measure and dimension separately when the source allows.

## Output of a run

Under `runs/<date>_run-NN/`: `requirements.jsonl`, `findings.jsonl`, `open_questions.jsonl`,
`manifest.json`, `review.md`. Never write into `registers/` — the human merges.

`review.md` leads with what a human must decide now, then the confidence distribution, then what
was **deliberately not concluded**. Template in `run-layout.md`.

## Calibrate before scaling

Before processing thirty documents, process one that the client knows well. Have them review the
register for that document. The fraction of records they correct is this project's error rate;
if it is high, fix the approach — usually the locator scheme or the granularity — before
continuing. This measurement is cheap and worth more than any planning.

## Failure modes

| Failure | Sign |
|---|---|
| Narrative instead of register | Paragraphs; no `locator` |
| Smoothing conflicts | Two sources, one confident sentence, empty `conflicts[]` |
| Inference without a question | `kind: inferred` with no `open_questions` entry |
| Priorities from tone | `priority: must` on a record whose source never says so |
| Department as owner | `owner: "Finance"` |
| Reading tier-zero docs as truth | Identifiers copied from a draft wiki, never verified |
| Granularity too coarse | Records with "and" in `statement` |

## Reference files

- `../discovery-intake/references/run-layout.md` — schemas, templates. Required reading.
- `references/extraction-patterns.md` — worked examples by source type (spec, transcript,
  ticket, deck), including how to write locators for each.
