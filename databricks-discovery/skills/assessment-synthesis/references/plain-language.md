# Two registers of language — and the words for each

The registers use short codes so records diff, group and sort. The client reads the report, not the
registers. Every code therefore has a plain label, and the generator renders the label, not the code.

## The split

| | §0 – §5 — business | §6 onward — technical |
|---|---|---|
| Read by | sponsor, CFO, business owners, steering committee | architect, DBA, BI owner, delivery lead |
| May use | plain sentences, object names, dates, counts | register codes, **next to their plain label** |
| May **not** use | a status code, a register field name, an evidence tier, an ID as the subject of a sentence, a Databricks product name that Appendix A does not define, a file name in prose | — |
| Evidence | in a column called *Where to check*, never mid-sentence | inline `file:line` is fine |

`build_deliverables.py --strict-register` fails the build on a violation in §0 – §5; without the flag
it warns and names the line. The check reaches the four places prose enters the report:
`author-sections.md`, `open_questions.default`, `open_questions.question`, and `sufficiency.md`.
**Write those four in the business register in the first place** — the generator cannot rewrite prose.

## The labels the generator renders

Business-rule certainty (`rule_status`):

| Code | Printed as |
|---|---|
| `VERIFIED` | Confirmed — the code and the document agree |
| `CONFLICT` | Disputed — the code and the document disagree |
| `CODE-ONLY` | In the code only — no written specification |
| `DOC-ONLY` | In the specification only — never built |
| `CONFIG-ONLY` | In a configuration value, not in the code |
| `DEAD` | Not used by anything today |
| `UNRESOLVED` | Not yet traced to a source |

Review state (`status`): `extracted` → **Draft** · `reviewed` → **Checked** · `confirmed` →
**Signed off by owner** · `deferred` → **Deferred** · `rejected` → **Rejected**.

Scope decision (`disposition`): `migrate` → **Move as it is** · `modernize` → **Rebuild differently**
· `retire` → **Switch off** · `defer` → **Decide later** · none → **Not yet decided**.

Question impact (`impact_if_wrong`): `high` → **Blocks the decision** · `medium` → **Changes the
plan** · `low` → **Good to know**.

Evidence tier: `L0` a claim or a slide · `L1` an interview or a document · `L2` the source code ·
`L3` a measurement on the live system. **Never print `L3` in prose** — write "needs a measurement on
the live system".

Other renamings: *Axis C* → **the decision this report has to serve** · *rationalization* → **scope
decision** · *dependency cone* → **everything this report depends on, and nothing else** ·
*orphan* → **nothing has read it inside the usage window**.

## Complexity — use Lakebridge's four words

`Simple · Medium · Complex · Very Complex`, and nothing else. They are the buckets the Lakebridge
Analyzer emits, so our §12 and the Analyzer workbook the client will eventually see are one scale,
not two. The generator maps `low/high/very high` onto them and warns on anything it cannot map.
`complexity_source` must be `analyzer` for the number to count as measured; `manual` is triage and
the report says so on its face.

## Glossary

`GLOSSARY` in `scripts/build_deliverables.py` holds the one-line definition for every Databricks term
the report is allowed to use. Appendix A prints **only the terms the finished report actually used** —
a glossary of unused words is furniture. Using a Databricks term that is not in that dict is the
signal to add it there, not to leave it undefined.
