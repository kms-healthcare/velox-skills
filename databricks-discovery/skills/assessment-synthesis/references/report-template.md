# Report and workbook — what each section is generated from

`scripts/build_deliverables.py` renders both. Author prose enters only through
`author-sections.md` (`## decision`, `## architecture`, `## drivers`, `## risks`).

| Report section | Register / file | Notes |
|---|---|---|
| 1 Decision and recommendation | `intake.md` Axis C + `## decision` | the one page leadership reads |
| 2 Decisions required | `open_questions` where `impact_if_wrong = high`, open | owner, blocking, default |
| 3 Scope — rationalization summary | `rationalization.jsonl` | counts by kind × disposition; retire list with `owner_agreed`; manual-complexity warning |
| 4 What the evidence does not support | `sufficiency.md` ❌ ⚠️ rows | up front, not appendix-only |
| 5 Key findings | `findings` top 10 by severity | locator per row |
| 6 Business rules at risk | `business_rules` `CONFLICT` / `CODE-ONLY` / `CONFIG-ONLY` + status distribution | |
| 7 Requirements | `requirements` counts by type × status; inferred list | |
| 8 Target architecture | `## architecture` + Mermaid from `dependency_edges` | placeholders stay visible |
| 9 Waves, pilot, drivers | `rationalization.wave`, `inventory.complexity(_source)`, `## drivers` | |
| 10 Risks and cost flags | `## risks` | |
| 11 Open questions by person | `open_questions` grouped by `ask` | |
| App. C Sufficiency | `sufficiency.md` verbatim | |
| App. D Sources | `runs/*/manifest.json`; count of records still `extracted` | |

Workbook tabs: Summary · Decisions · Rationalization · Findings · Business Rules · Requirements ·
Inventory · Open Questions (+ `email_draft`) · Traceability (req → rules → objects → questions) ·
Dependencies · Sufficiency · Sources. Every tab has filters and a `locator`/`evidence` column.

Rules for both: a number without a locator is deleted; `extracted` records are excluded unless
`--include-unreviewed`; `<catalog>` placeholders are never cosmetically resolved.
