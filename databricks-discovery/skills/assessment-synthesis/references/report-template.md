# Report and workbook — what each section is generated from

`scripts/build_deliverables.py` renders both. Author prose enters only through
`author-sections.md`, which has eight headings: `## summary`, `## decision`, `## success`,
`## architecture`, `## governance`, `## business_case`, `## drivers`, `## risks`.

**§0 – §5 are the business register, §6 onward the technical one** — see `plain-language.md`.
The generator warns (or, with `--strict-register`, fails) when internal vocabulary reaches §0 – §5.

| Report section | Register / file | Notes |
|---|---|---|
| 0 In five lines | `## summary` + computed fact strip | answer first: decision, scope settled, who we wait on, decisions taken on our default, what evidence will not carry, rule certainty |
| 1 Decision and recommendation | `intake.md` decision line + `## decision` | the one page leadership reads |
| 2 Decisions required | `open_questions` where `impact_if_wrong = high`, open | decision sentence leads; owner, default; **ID in the last column**. A second table lists questions already running on a default (`answer_kind: assumed-default`), and a note counts `user-relayed` answers |
| 3 Scope — move / rebuild / switch off / decide later | `rationalization.jsonl` | counts by kind × disposition, printed as plain labels; switch-off list with an *Owner has agreed* and a *Where to check* column; manual-complexity warning |
| 4 What the evidence does not yet support | `sufficiency.md` ❌ ⚠️ rows | up front, not appendix-only; legend printed above the table |
| 5 How we will know it worked | `success_criteria.jsonl` + `## success` | metric, today, target, measured how, who signs, wave. Empty is itself the finding |
| 6 Key findings | `findings` top 10 by severity | finding sentence leads; locator column; ID last |
| 7 Business rules at risk | `business_rules` certainty distribution, then `CONFLICT` / `CODE-ONLY` / `CONFIG-ONLY` rows | code and plain label side by side |
| 8 Requirements | `requirements` counts by type × review state; inferred list | column heads are Checked / Signed off / Deferred / Draft |
| 9 Target architecture | `## architecture` + Mermaid from `dependency_edges` | diagram uses **real object names**, grouped by layer, scoped to wave 1 |
| 10 Platform foundation — governance and landing zone | `## governance` | catalog and workspace layout, identity, network, secrets, CI/CD, monitoring, cost controls |
| 11 Source → target technology mapping | `TECH_MAP` in the generator, overridden by `technology_map.jsonl` | only kinds present in `inventory`; shape of the work, not an estimate |
| 12 Waves, pilot, estimate drivers | `rationalization.wave`, `inventory.complexity(_source)`, `## drivers` | complexity on the Lakebridge scale, with how it was scored |
| 13 Business case inputs | `## business_case` | what a cost comparison still needs; no saving is asserted |
| 14 Risks and cost flags | `## risks` | |
| 15 Open questions by person | `open_questions` grouped by `ask` | routing list only — first clause + ID; high-impact ones point at §2 |
| App. A Glossary | `GLOSSARY` in the generator | **only terms the finished report used** |
| App. B How to read this report | generator constants | evidence marks, ID prefixes, rule certainty, review state, **answer provenance**, evidence tier, disposition |
| App. C Sufficiency | `sufficiency.md` verbatim | |
| App. D Sources | `runs/*/manifest.json`; count of records still Draft | |

Workbook tabs: Summary · Decisions · Rationalization · Findings · Business Rules · Requirements ·
**Success Criteria** · **Technology Map** · Inventory · Open Questions (+ `email_draft`) ·
Traceability (req → rules → objects → questions) · Dependencies · Sufficiency · **Glossary** ·
**Approvals** (`manifest.json` `approvals[]` + `external_access` — one row per gate that was asked
for and granted) · Sources. *Open Questions* keeps answered rows, with `answer_kind`, `answered_by`
and `answered_at`: dropping them loses the only record of who decided what, on whose authority. Every tab has filters, a `locator`/`evidence` column, and — where a register carries a code —
both the raw code (what you filter on) and its plain label next to it.

Rules for both: a number without a locator is deleted; `extracted` records are excluded unless
`--include-unreviewed`; `<catalog>` placeholders are never cosmetically resolved; complexity is one
of `Simple · Medium · Complex · Very Complex` or it is `null`.
