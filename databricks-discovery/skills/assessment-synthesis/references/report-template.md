# Report and workbook — what each section is generated from

`scripts/build_deliverables.py` renders both. Author prose enters only through
`author-sections.md` (`## decision`, `## architecture`, `## roadmap`, `## drivers`, `## risks`).
Part A describes what is there and is generated tables only; Part B is what to do about it. A
section with no records behind it prints one sentence — *insufficient evidence; needs X; risk if
skipped Y* — never filler.

| Report section | Register / file | Notes |
|---|---|---|
| **Part A — Discovery** | | |
| 1 Executive summary | `intake.md` Axis C · `readiness.jsonl` · `findings` · `## decision` · `sufficiency.md` ❌ ⚠️ | readiness per dimension and overall; top 5 risks (critical/high, `carried` first); recommendation; what the evidence does not yet support |
| 2 Business context & target-state requirements | `intake.md` Axis A · `requirements` | counts by type × status; NFR / security / scope / integration rows first (SLAs, residency live there), then the use cases |
| 3 Data landscape & current-state architecture | `inventory` | counts by kind with `holds_pii`; every store (`table`, `file_store`, `queue`, `log`, `cache`, `object_store`, `export`, `view`) with volume; complexity by source |
| 4 Workload catalogue | `inventory` — every kind that is not a store | frequency = `schedule`; volume = rows / GB / runs / runtime; `owner` (NOT SET is counted) |
| 5 Dependencies & lineage, incl. external services | `dependency_edges` · `inventory` `external_consumer` | an edge end with no inventory record is listed as an external or unmapped service; Mermaid DAG |
| **Part B — Assessment** | | |
| 6 Governance, PII & GDPR gaps | `inventory.holds_pii` / `erasure_reaches` · `findings` category `governance` | every PII surface erasure is not proven to reach |
| 7 Databricks security posture | `readiness.jsonl` `security` · `findings` category `security` | **scored only with `basis` `sat` or `workspace`**; otherwise "not scored — needs a SAT run" and the code-level gaps |
| 8 Technical debt register | `findings` — every other category | disposition and evidence-kind counts over all findings; `carried` first |
| 9 Migration complexity & scope | `rationalization` · `business_rules` | decided share; kind × disposition; per object complexity (source) and wave; retire list; rules at risk (`CONFLICT` / `CODE-ONLY` / `CONFIG-ONLY`) |
| 10 Target architecture & component mapping | `## architecture` · `rationalization.target_component` | placeholders stay visible |
| 11 Recommendations, phased roadmap & cost estimate | `## roadmap` · `rationalization.wave` · `## drivers` | the cost is labelled an estimate: drivers and a range with its assumptions; the price is the delivery lead's |
| 12 Risk register, assumptions & open decisions | `## risks` · `findings` critical/high · every `inferred` record · `open_questions` high-impact, open | owner, blocking, default per decision |
| **Appendix** | | |
| A Evidence | `sufficiency.md` verbatim · count of records still `extracted` | sources read: workbook tab *Sources* |
| B Best-practice references | every `evidence[]` with `kind: external` | reference → the records it supports |
| C Stakeholder questionnaire | `open_questions` grouped by `ask` | full text; high-impact ones point at §12; email drafts in the workbook |

## Readiness — the three rules for a number

1. **A dimension is scored 1–5 only with a locator**; otherwise "not scored — needs X" (`needs`).
2. **Overall = the lowest dimension.** With any dimension unscored it reads "at most N", because an
   unscored one can pull it lower.
3. **Security is scored only from SAT output or workspace evidence** (`basis: sat | workspace`). A
   score from code reading is refused; the code-level gaps still appear in §7.

Dimensions: `data` · `logic` · `governance` · `security` · `operations`. Schema: `run-layout.md`.

Workbook tabs: Summary · Readiness · Decisions · Rationalization · Findings · Business Rules ·
Requirements · Inventory · Open Questions (+ `email_draft`) · Traceability (req → rules → objects →
questions) · Dependencies · Sufficiency · Sources. Every tab has filters and a `locator`/`evidence`
column.

Rules for both: a number without a locator is deleted; `extracted` records are excluded unless
`--include-unreviewed`; `<catalog>` placeholders are never cosmetically resolved.
