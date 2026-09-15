# Assessment report — template and the register behind each section

Every section names the register it is generated from. If a section has no register, it has no
content.

## `rationalization.jsonl` — schema

```json
{ "object_id": "tbl-0087", "kind": "table", "name": "MP_DWH.dbo.STG_POS_TXN",
  "disposition": "migrate",
  "criteria": { "used": true, "usage_window_days": 396, "covers_month_end": true,
                "complexity": "medium", "on_critical_path": false,
                "rule_status_max": "CODE-ONLY", "owner_agreed": null },
  "evidence": [{ "source_id": "src-usage-01", "locator": "querystore_export.csv:row 412", "kind": "stated" }],
  "blocking": [], "wave": 1, "notes": null }
```

`disposition`: `migrate | modernize | retire | defer`. `owner_agreed` is `null` until a person says
yes; `retire` with `owner_agreed: null` is a *recommendation*, shown as such.

---

## Report skeleton (`assessment-report.md`)

```markdown
# <Project> — Discovery & Assessment          <date> · version · authors

## 1. Decision and recommendation                         ← intake.md Axis C + rationalization summary
> This report is for **<who>** to decide **<what>** before **<when>**.
Recommendation: …  Conditions: …  What we could not conclude and why: … (one line, links §4)

## 2. Decisions required                                  ← open_questions where impact_if_wrong = high
| # | Decision | Owner | By | Cost of delay |

## 3. Scope — rationalization summary                    ← rationalization.jsonl
| Kind | migrate | modernize | retire | defer | undecided |
Top retire candidates (name, last read, owner to confirm) · Top modernize items (name, finding)

## 4. What the evidence does not yet support             ← sufficiency.md ❌ and ⚠️ rows
| Conclusion | Missing | Risk if skipped | Requested on |

## 5. Key findings                                        ← findings.jsonl, severity desc, top 10
| # | Finding | Impact | Evidence | Raises |

## 6. Business rules at risk                              ← business_rules.jsonl where rule_status ∈ {CONFLICT, CODE-ONLY(high)}
rule_status distribution · table of CONFLICT rules with both sides and the owner to ask

## 7. Requirements                                        ← requirements.jsonl
counts by type × status · must-haves with owner and status · inferred requirements awaiting confirmation

## 8. Target architecture outline                         ← rationalization + findings + requirements(type=data/security)
catalog/schema proposal (placeholders unless agreed) · medallion placement by logic class ·
ingestion pattern per source · orchestration shape (Mermaid from dependency_edges) ·
security inputs · decisions left to the architect

## 9. Waves, pilot, estimate drivers                      ← rationalization.wave, dependency_edges, inventory complexity
| Wave | Objects | Prerequisites | Reconciliation baseline | Exit criterion |
Pilot rationale · driver table with confidence and evidence

## 10. Risks and cost flags                               ← findings (severity≥high) + project-type cost flags
| Risk | Owner | Mitigation | Deadline |

## 11. Open questions by person                           ← open_questions grouped by ask
## Appendix A — Full rationalization matrix
## Appendix B — Traceability  requirement → rules → objects → questions
## Appendix C — Evidence sufficiency table
## Appendix D — Sources and run manifests
## Appendix E — Method: reading order, usage window, calibration error rate
```

## Writing rules for the generator and for humans

- A number without a locator is deleted.
- `extracted` (unreviewed) records are excluded from sections 1–10; they may appear in Appendix D
  as "pending review: N".
- Placeholders stay visibly placeholders: `<catalog>`. Do not resolve them cosmetically.
- Sections 1–4 ≤ 5 pages. If longer, the report is describing, not deciding.
