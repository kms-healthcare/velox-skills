# Run layout, register schemas, and record budget

One principle: **machine-readable first, human-readable second**. Registers are JSONL (one record
per line) so they diff, merge, and feed the next skill. Everything a person reads — the workbook,
the report, the docx — is **generated** from them by
`assessment-synthesis/scripts/build_deliverables.py`. Nobody hand-writes a report.

Records link by `id`. Prefixes: `FR-` functional, `DR-` data, `SEC-` security, `NFR-`
non-functional, `SCOPE-`, `INT-` integration, `BR-` rule, `obj-` inventory, `FND-` finding,
`OQ-` question, `src-` source.

## Layout

```
discovery/<project>/
├── intake.md · source_request.md · sufficiency.md
├── registers/            # source of truth — only a human merges here
│   ├── requirements.jsonl        business_rules.jsonl     inventory.jsonl
│   ├── dependency_edges.jsonl    findings.jsonl           open_questions.jsonl
│   └── rationalization.jsonl     (set by assessment-synthesis)
└── runs/<date>_run-NN/   # the agent writes here, never into registers/
    ├── manifest.json     # sources (path + sha256), external access, counts
    ├── *.jsonl           # new / changed records only, status = extracted
    └── review.md         # one page for the reviewer

# next to the project dir, generated:
discovery-<project>.xlsx · assessment-report.md · assessment-report.docx
```

Sources are **referenced by path + sha256 in `manifest.json`**, not copied. Only originals that may
move (email bodies, chat exports) get a copy under `sources/`.

## Record budget — cost discipline

| Field | Limit | Why |
|---|---|---|
| `evidence[].excerpt` | ≤ 120 chars | The locator is the proof; the excerpt is a hint |
| `evidence[]` per record | 1, or 2 when two sources agree; conflicts go in `conflicts[]` | A third quote adds cost, not certainty |
| `findings.detail`, `requirements.statement` | ≤ 300 chars | If it needs more, it is two records |
| `open_questions` sent to the user per turn | ≤ 5 | The rest stay in the register |
| Reports | **one**, generated; author fills `## decision`, `## architecture`, `## drivers`, `## risks` in an `author-sections.md` passed to the generator | Writing a second report by hand doubled the output last time and added nothing |
| Author sections | `decision` ≤ 400 · `architecture` ≤ 500 · `drivers` ≤ 300 · `risks` ≤ 400 words (the generator warns past these) | Uncapped, they grew to 1,900 words and pushed the report past twelve pages. Prose past the budget is description; a decision is short |
| The chat reply | ≤ ~300 words: conclusion · files written · ≤ 5 questions · what you did not conclude | The report and workbook are the deliverables. Restating them in chat is a third copy that carries no locator |

## Three fields every register carries

| Field | Values | Rule |
|---|---|---|
| `evidence[].kind` | `stated` · `inferred` · `external` | Conclusions rest on `stated` only. `inferred` always raises an open question. `external` (a law, vendor docs) may support a finding's *impact* or a requirement's rationale, never a fact about the client's system, and names its reference |
| `evidence[].locator` | `file:line` · `p.N §x` · `speaker, date, hh:mm:ss` · `sheet!cell` · `ticket-id` · `object_name` | Openable in 5 seconds. **No locator, no record** |
| `status` | `extracted` → `reviewed` → `confirmed` · `rejected` · `deferred` | The agent sets only `extracted`; humans move it |

Also: `confidence` 0–1 (orders review, never skips it), `inferred` bool, `conflicts[]` (kept apart from
evidence — disagreement is a finding, not proof).

## Schemas (one example each)

```json
// requirements.jsonl   type ∈ functional|data|security|nonfunctional|scope|integration ; priority only if a source states it
{"id":"FR-01","type":"functional","title":"Net revenue excludes returns ≤7 days, status 9, store HCM-99",
 "statement":"Daily net revenue = valid transactions minus returns within 7 days; status 9 and HCM-99 excluded.",
 "domain":"sales","priority":null,"status":"extracted","confidence":0.9,"inferred":false,
 "evidence":[{"source_id":"src-sp-014","source_type":"code","locator":"sp_Calc_Daily_Revenue.sql:45-52",
              "excerpt":"WHERE t.status <> 9 AND t.store_cd <> 'HCM-99'","kind":"stated"}],
 "conflicts":[{"source_id":"src-spec-2016","locator":"§4.1","note":"spec mentions none of the three"}],
 "open_questions":["OQ-07"],"related_rules":["BR-012","BR-013"],
 "target_mapping":{"layer":"silver","object":"<catalog>.silver.transactions"},"owner":null,
 "extracted_by":"requirements-extraction@0.2.0","extracted_at":"2026-09-14T09:12:00+07:00"}

// business_rules.jsonl   rule_status ∈ VERIFIED|CONFLICT|CODE-ONLY|DOC-ONLY|CONFIG-ONLY|DEAD|UNRESOLVED
{"id":"BR-012","name":"Exclude test transactions","logic":"status <> 9",
 "plain":"Transactions with status 9 are test data and never count as revenue",
 "anchor":{"identifier":"dbo.sp_Calc_Daily_Revenue","hash":"a3f9…"},
 "evidence":[{"source_id":"src-sp-014","locator":"sp_Calc_Daily_Revenue.sql:45","kind":"stated"}],
 "rule_status":"CODE-ONLY","in_spec":false,"config_driven":false,
 "requirements":["FR-01"],"open_questions":["OQ-07"],"status":"extracted"}

// inventory.jsonl   kind ∈ table|view|procedure|ssis_package|job|report|external_consumer|…
// complexity_source ∈ analyzer|manual|null — a manual tier is triage, never presented as measured
{"id":"obj-0087","kind":"table","name":"MP_DWH.dbo.STG_POS_TXN","layer_guess":"bronze",
 "row_estimate":730000000,"size_gb":412,"writers":["obj-0031"],"readers":["obj-0044","obj-0112"],
 "last_read_at":"2026-09-09","last_write_at":"2026-09-13","orphan":false,
 "pii_candidates":[],"complexity":null,"complexity_source":null,"disposition":null,
 "evidence":[{"source_id":"src-usage-01","locator":"querystore_396d.csv:row 3","kind":"stated"}],"status":"extracted"}
// pipelines add: schedule, avg_runtime_min, run_as, reads[], writes[] ; reports add: consumers[], exec_count_90d, last_exec_at

// dependency_edges.jsonl   kind ∈ reads|writes|triggers|calls|depends_on — draw the DAG from this, never by hand
{"from":"obj-0031","to":"obj-0087","kind":"writes","evidence":[{"source_id":"src-ssis-01","locator":"pkg_pos_load.dtsx:18","kind":"stated"}]}

// findings.jsonl   severity ∈ critical|high|medium|low ; category ∈ data_quality|logic|security|cost|performance|governance|scope|dependency|documentation
{"id":"FND-03","severity":"high","category":"data_quality",
 "title":"3% of POS transactions dropped silently by INNER JOIN to DIM_STORE",
 "detail":"sp_Calc_Daily_Revenue:61 INNER JOINs dim_store; no unmatched handling, nothing logged.",
 "impact":"Reported revenue understated by unmatched share; magnitude needs profiling (L3).",
 "evidence":[{"source_id":"src-sp-014","locator":"sp_Calc_Daily_Revenue.sql:61","kind":"stated"}],
 "requirements_raised":["DR-01"],"questions_raised":["OQ-11"],"status":"extracted"}

// open_questions.jsonl   ask = a person (role + "(name: ?)" if unknown), never a department
{"id":"OQ-07","question":"Is HCM-99 still excluded from revenue? Since when, and who owns the rule?",
 "why":"In code, not in spec; affects the largest store code.",
 "evidence":[{"source_id":"src-sp-014","locator":"sp_Calc_Daily_Revenue.sql:52","kind":"stated"}],
 "ask":"Head of Accounting (name: ?)","default":"Keep current behaviour; mark CONFLICT",
 "impact_if_wrong":"high","blocking":["FR-01","BR-014"],"status":"open","answer":null}

// rationalization.jsonl   disposition ∈ migrate|modernize|retire|defer ; set only by assessment-synthesis
{"object_id":"obj-0087","kind":"table","name":"MP_DWH.dbo.STG_POS_TXN","disposition":"migrate","wave":1,
 "criteria":{"used":true,"usage_window_days":396,"covers_month_end":true,"complexity":null,"complexity_source":null,
             "on_critical_path":false,"rule_status_max":"CODE-ONLY","owner_agreed":null},
 "evidence":[{"source_id":"src-usage-01","locator":"querystore_396d.csv:row 3","kind":"stated"}],"blocking":[],"notes":null}

// manifest.json   external_access lists every call beyond local files (endpoint, statement, rows) — empty = pure file read
{"run_id":"2026-09-14_run-07","skill":"requirements-extraction@0.2.0","model":"<model id>","project":"minhphat-migration",
 "sources_read":[{"source_id":"src-sp-014","path":"<path>/sp_Calc_Daily_Revenue.sql","sha256":"…","bytes":18402}],
 "sources_requested_not_available":["src-querystore"],"external_access":[],
 "counts":{"requirements":12,"business_rules":31,"findings":4,"open_questions":9},
 "notes":"Docs loaded after code (code-first rule)."}
```

## Markdown templates

**`intake.md`**
```markdown
# Intake — <project>  (run-NN, <date>)
## Axis A — type:  primary **<type>** `inferred|stated` — <driver, locator> · secondary <type> · to confirm: OQ-xx
## Axis B — inputs per source system
| System | Level | In hand (source_id) | Missing to reach next level |
## Axis C — decision
> This report is for **<who>** to decide **<what>** before **<when>**.  `assumed|stated` — OQ-xx
## Blocking questions this turn (≤5)
```

**`source_request.md`** — tiers *Required / Recommended / Optional*; columns
`# | Source | Why | How to obtain | Client owner | Status (✅ src-id · ⏳ requested <date> · ❌)`.
Line 1 is always the access request.

**`sufficiency.md`** — `| Conclusion needed | Evidence required | In hand | State ✅⚠️❌ | If missing |`.
Always include a **Usage window** row: log source, start, end, and the last service restart when
any usage comes from DMVs (`dm_exec_*` resets on restart).

**`review.md`** — one page: read (sources, order) · produced (counts) · **needs a human now** (≤5) ·
`rule_status` distribution · unsure (confidence < 0.6) · **deliberately not concluded** · how to merge.

**`author-sections.md`** (input to the generator) — four headings, prose only:
`## decision` · `## architecture` · `## drivers` · `## risks`.
