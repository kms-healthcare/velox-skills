---
name: assessment-synthesis
description: >
  Use when discovery registers exist and a decision has to come out of them. Triggers: "write the
  assessment report", "what do we migrate and what do we retire", "estimate the migration", "build
  the roadmap / waves", "summarise discovery for the steering committee", "prioritise the backlog
  from discovery", "give me the Excel for the client", or discovery-intake's sufficiency gate
  reporting that the registers are ready. Also for turning SAT output or system-table analysis into
  client-facing requirements and risks. Not for extracting requirements or reading code — those
  registers must already exist.
compatibility: Python 3.9+ with openpyxl for scripts/build_deliverables.py; pandoc optional for .docx.
metadata:
  version: "0.3.0"
parent: discovery-intake
---

# Assessment synthesis — from registers to decisions

Done means: the person the report is written for can make the decision it was written for, and
defend it with evidence someone else can check. Not: every template section has text. Twelve pages
that settle scope beat sixty that describe the current state.

**Nothing is hand-written except eight author sections.** The workbook and the report are generated
by `scripts/build_deliverables.py` from `registers/`; you write `author-sections.md` with
`## summary` (≤ 120 words), `## decision` (≤ 400), `## success` (≤ 150), `## architecture` (≤ 500),
`## governance` (≤ 300), `## business_case` (≤ 250), `## drivers` (≤ 300), `## risks` (≤ 400), and
pass it in — the generator warns when a section runs over or is missing. A statement with no record
behind it is either given a record (with a locator) or deleted. Schemas:
`../discovery-intake/references/run-layout.md`.

## Two registers of language — the rule that breaks reports

§0 – §5 are read by a sponsor, a CFO and business owners. **They may not contain a status code, a
register field name, an evidence tier (`L2`), an ID as the subject of a sentence, a file name in
prose, or a Databricks product name that Appendix A does not define.** §6 onward is for the
architect and the DBA and may use the codes, always beside their plain label. The generator renders
every code through a label map and checks §0 – §5; `--strict-register` makes a violation fatal.

It cannot rewrite prose, so **write these four in the business register in the first place**:
`author-sections.md`, `open_questions.question`, `open_questions.default`, `sufficiency.md`.
"Keep 10,000; mark BR-04 CONFLICT" is a note to ourselves. "Keep 10,000 — and record that the spec
says otherwise and nobody has reconciled the two" is a default a CFO can accept or overturn.
Labels, renamings and the glossary: `references/plain-language.md`.

## Working in a chat — gates before the client sees anything

`../discovery-intake/references/interaction-protocol.md` binds here, and this is the skill where its
gates are outward-facing:

- **The email drafts in the workbook's *Open Questions* tab are drafts.** The agent never sends
  them, never contacts anyone in `ask`, and says so when it hands the workbook over.
- **A deliverable already sent to the client is not overwritten.** Write beside it under a new name
  and say both exist; someone is quoting the old one.
- **`owner_agreed: true` requires `answer_kind: client-confirmed`** — the named owner, with a
  locator. The engineer agreeing in chat is `user-relayed` and leaves the retire recommendation a
  recommendation. §3 prints the ratio on its face, so this is visible whether or not anyone reads
  the register.
- **Applying a default is an event, not a silence.** Say it in the turn, set
  `answer_kind: assumed-default`, keep the row in §2, and name what changes if it turns out wrong.
  §0 counts them.

## The Iron Law

```
NO NUMBER WITHOUT A LOCATOR.
NO EFFORT FIGURE WITHOUT A MEASURED TRANSPILE RATE.
```

**Violating the letter of these rules is violating the spirit of these rules.** A range is a number.
So is "roughly", "on the order of", and a chart with no axis.

## Red Flags — stop before you write it

- Writing "approximately", "a range of", "on the order of" about effort while `complexity_source`
  is anything but `analyzer`
- A `retire` row whose usage window is under 90 days, or does not cover a month-end and a quarter-end
- A `migrate` row on an object that carries a `CONFLICT` rule
- Extrapolating a count from the objects you read to the estate the deck claims
- Synthesising from `runs/` because `registers/` is empty
- A §0–§5 sentence you would not read aloud to a CFO
- Sending deliverables while `build_deliverables.py` is still printing warnings

**Every one of these means: the record is not ready, or the reader is the wrong one.**

## Rationalizations

| Excuse | Reality |
|---|---|
| "The client asked for a number — a range is fine" | A range without a measured transpile rate is an invented number with error bars drawn around it. §12 gives drivers and says what must be measured. |
| "The deck says 340 tables; extrapolating from the 15 we read is reasonable" | 15 of 340 is 4%. Extrapolation from 4% is invention. §4 names the gap and what closes it. |
| "`owner_agreed` is a formality — the usage log is conclusive" | The log proves nobody read it. Only an owner knows whether that is correct. Switching off an unclaimed table is our risk, not theirs. |
| "The rule is disputed but the code is unambiguous — migrate it" | Migrating a disputed rule faithfully delivers wrong numbers with a certificate. `CONFLICT` cannot be `migrate`. |
| "Registers are empty but the runs are good — I'll synthesise from those" | That is exactly what the Gate forbids. A human merge is the review. |
| "Complexity by eye is close enough to get started" | Then it carries `complexity_source: manual`, and the report says on its face that no tier was measured. |
| "No success criteria were given, so §5 stays empty and quiet" | An empty §5 means nobody can call this a success or a failure later. Say that in `## summary`. |
| "The linter warnings are cosmetic" | They mark the sentences a sponsor cannot look up. Fix them or run `--strict-register` and find out. |

## Gate

Synthesise from `registers/` after human merge, never from unreviewed `runs/` batches. Re-run the
sufficiency check against the decision the report serves; a ❌ conclusion still gets its one-sentence
section, and §0 names the decision that cannot yet be made and the cost of waiting.

## 1. Rationalization matrix → `rationalization.jsonl`

| Disposition | Printed as | Criteria — all with evidence | Typical share |
|---|---|---|---|
| **retire** | Switch off | no readers in a usage window ≥ 90 days incl. month-end and quarter-end; on no scheduled path; no consumer claims it; **an owner has agreed or been asked** | 20–40% of a 10-year DW |
| **migrate** | Move as it is | used; low/medium complexity; rules `VERIFIED` or low-impact `CODE-ONLY`; no critical-path finding | the bulk |
| **modernize** | Rebuild differently | on the critical path with a structural finding (serial chain, full rebuild, cursor); or logic that belongs in Silver / metric views rather than N copies | 10–20%, most of the value |
| **defer** | Decide later | blocked on a `CONFLICT`; owned by a system being replaced; outside the decision's scope | whatever is honest |

No `retire` without usage evidence — missing log → `defer` + question, and the report says how much
scope is undecided because of it. Objects with `CONFLICT` rules cannot be `migrate`: migrating a
disputed rule faithfully delivers wrong numbers with a certificate.

**Complexity is one of `Simple · Medium · Complex · Very Complex`** — Lakebridge Analyzer's own
buckets, so our table and the Analyzer workbook the client eventually sees are one scale. It carries
`complexity_source`; only `analyzer` counts as measured, `manual` is triage and the report says so.

## 2. Waves and pilot

Order by dependency depth, business criticality, rule certainty. The pilot is **a business-visible
report of moderate complexity whose upstream dependencies are few and fully known** — the CFO's
revenue report, not the easiest table. Each wave: objects, data prerequisites (access, CDC,
conflicts settled), reconciliation baseline, exit criterion. Waves without prerequisites are fiction.

## 3. Success criteria → `success_criteria.jsonl`

Databricks treats measurable KPIs as an output of assessment, not of delivery, and it is right: a
migration with no agreed criterion cannot be declared a success or a failure afterwards. One record
per criterion: `metric`, `today` (measured, with a locator — not "slow"), `target`, `measured_by`
(the same way on both platforms), `owner` (a person), `wave`. Draw them from the evidence you
already have: NFR requirements, the job-history numbers behind the batch-window finding, the cost
driver, the reconciliation baseline. A criterion with no owner and no measurement is a wish, and the
report prints it as one. **An empty §5 is itself the finding** — say so in `## summary`.

## 4. Estimate drivers, not prices (`## drivers`)

Object counts by kind × complexity (Analyzer) · **trial transpile rate on 10–20 objects across
tiers — run it during assessment; without it give a range and say so** · count of `CONFLICT` and
high-impact `CODE-ONLY` (calendar time with owners, not effort) · critical-path re-architecture items
· sources without CDC/watermark · `CONFIG-ONLY` migration · backfill depth × volume · missing
reconciliation baselines · consumers to re-point. Each with confidence and evidence; a driver from
an interview or a slide is labelled a guess.

## 5. Business case inputs (`## business_case`)

Databricks anchors its whole assess phase on TCO. We do not assert a saving we cannot evidence — but
we do say exactly what a cost comparison still needs and who holds it: current licence and
infrastructure cost, the renewal quote, the consumption estimate from the target design, the cost of
the deadline the client is trying to beat. Name the holder of each missing input and the date it is
needed by. "No saving is asserted in this report" belongs in §13 in those words.

## 6. Target architecture outline (`## architecture`)

Domain level unless names are verified. Catalog/schema topology with the trade-off stated;
medallion placement of the *classes* of logic found (landing → bronze; conformance and
`VERIFIED`/`CODE-ONLY` rules → silver; measures → **Unity Catalog metric views**; access views →
gold); ingestion pattern per source from its change-detection mechanism; orchestration shape from
the DAG — name the parallelisable branches. List the decisions that are the architect's. Object
names stay `<catalog>` placeholders until agreed. The diagram is generated from `dependency_edges`
with real object names, grouped by layer, scoped to wave 1 — never hand-drawn.

`technology_map.jsonl` overrides the built-in source-kind → Databricks target table when this estate
needs it (§11). The built-in map is in `scripts/build_deliverables.py`.

## 7. Platform foundation (`## governance`)

The decisions made once, before wave 1, expensive to change after — Databricks ships this as a
deliverable of its own and so do we: workspace and catalog layout, identity and group model, network
and storage, secret management, CI/CD, monitoring, cost controls and budget policies. Drive it from
findings, not from a template: PII findings → tags and masks; shared accounts → a service principal
per workload; SAT checks → `SEC-` requirements with the check id as locator.

## 8. Risks and requirements from findings (`## risks`)

Every finding with `severity ≥ high` → a risk row (owner, mitigation, deadline) and usually a
requirement (`SEC-`, `NFR-`, `DR-`). Client-owned shared-responsibility items → `NFR-` marked
client-owned. Cost flags from the type module with the breaker question and the client's answer.

## 9. Generate

```
python3 scripts/build_deliverables.py discovery/<project> --author-sections author-sections.md
# add --strict-register to fail on internal vocabulary in §0–§5
# → discovery-<project>.xlsx · assessment-report.md · assessment-report.docx (pandoc)
```

Fix every register warning the generator prints before sending anything. Report sections 0–5
(five lines, decision, decisions required, scope, what evidence does not support, success criteria)
must fit five pages; if not, the assessment is describing, not deciding. Numbers carry locators; no
adjective without a number; recommendations are imperative and owned ("Switch off 112 tables —
owner: DBA lead, confirm by 10-01").

## References

`../discovery-intake/references/run-layout.md` — register schemas ·
`../discovery-intake/references/interaction-protocol.md` — turn contract, gates, how answers are recorded ·
`references/plain-language.md` — the two registers of language and every label ·
`references/report-template.md` — section ↔ register map and the workbook tabs ·
`scripts/build_deliverables.py --help`.
