---
name: security-posture
description: "Score a Databricks workspace's security posture against the Security Analysis Tool (SAT) check catalog - read-only, with every check passed, failed or reported as not assessed and why. Reads the live workspace through the Databricks CLI (GET only), imports SAT's own results when the client already runs SAT, and checks Terraform / bundle / grant SQL when there is no workspace yet. Writes security findings and the security readiness score into the discovery run. Use when asked for the security posture, a SAT-style check, the security section of the assessment, or a before/after security comparison of a migration. Never installs SAT or changes a setting."
compatibility: "Python 3.9+, stdlib only. Live mode needs the Databricks CLI signed in to the workspace (a read-only service principal by default)."
metadata:
  version: "0.1.0"
  parent: discovery-intake
---

# Security posture — SAT's checklist, read-only, scored in code

The client deliverable promises "Databricks security posture, scored", every finding pointing at
the check it fails and the best practice behind it. This skill does that without asking the client
for what SAT itself needs (an account-admin service principal, plus jobs, secrets and a warehouse
written into their workspace). **The checklist is SAT's** — the same check ids, severities and
documentation links (`references/sat-checks.json`, 65 checks) — and the evaluation is a script:
the agent judges what a failure means for the client, the code decides pass or fail and the score.

## Three sources — use every one you have

| Source | Command | Basis | When |
|---|---|---|---|
| Live workspace | `posture.py run --workspace [--profile <p>]` | `workspace` | a workspace exists and the CLI is signed in to it |
| SAT's own results | `posture.py sat-sql …` → run the SQL read-only → save rows as JSON → `--sat-results rows.json` | `sat` | the client already runs SAT; fills the 12 account-level and network checks a workspace identity cannot see |
| Infrastructure code | `--iac <repo path>` | `code` | pre-sales, or to compare the design with what is deployed |

Pass them together in one run; a check takes its answer from the live workspace first, then SAT,
then the code. **Code alone never scores** — it finds gaps, it cannot see the posture
(`assessment-synthesis` refuses a security score on `basis: code`).

```
python3 scripts/posture.py run --out discovery/<project>/runs/<date>_run-NN \
  --workspace --profile <profile> [--sat-results sat-rows.json] [--iac <repo>] \
  [--cloud aws|azure|gcp] [--allowed-regions '^eu-|europe']
python3 scripts/posture.py catalog      # what each check id is and how it is evaluated here
```

`--allowed-regions` comes from a residency requirement (`requirements.jsonl`, e.g. GDPR transfers)
— never from your own assumption. Without one, `VX-RES-1` stays not assessed.

## What it writes (into the run, never `registers/`)

- `posture.json` — all checks: `pass` / `fail` / `not_assessed` + reason, observed value, locator.
- `findings.jsonl` — one `FND-SEC-<check_id>` per failure, `category: security`, SAT severity,
  evidence[0] the observation (`GET /api/…  → key=value`, a SAT `run_id`, or `file:line`), evidence[1]
  the best practice (`kind: external`, the SAT documentation link). Stable ids: a second run on the
  same workspace replaces, it does not duplicate — that is what makes a before/after comparison.
- `readiness.jsonl` — `RDY-security` with the computed score, its basis, and `needs` listing every
  not-assessed group. Scoring: severity-weighted pass share over assessed checks (high 3, medium
  2, low 1) mapped to 1–5; any failed high check caps it at 3, three or more at 2.
- `manifest.json` — every GET appended to `external_access`.

## Not assessed is an answer, not a gap to fill

Account-level checks (customer-managed keys, private connectivity, account IP lists, audit log
delivery…) need account admin, which a read-only identity does not have; compute checks need a
cluster run; some settings do not exist on the client's pricing tier. Each is listed as **not
assessed, with the reason**, in `readiness.needs` and therefore in report §7 — never guessed, never
silently dropped. If the client wants them scored, the answer is SAT results or an account-admin
read, and that is an open question to the client's platform owner, not something to work around.

## Reviewing what it found

The findings are `extracted`; a person accepts or rejects each one before it reaches the report.
Expect to reject some on purpose — SAT's rules are generic: `GOV-21` flags a metastore whose owner
is the account that created it, which is normal on a Databricks-managed metastore. Write why in the
rejection; do not edit the script to hide a check for one client.

## Before / after a migration

Run it on the source-side workspace (or the client's landing zone) during assessment and again on
the target after each wave. Same check ids, same finding ids: a check that passed before and fails
after is a security regression the migration introduced, and it goes in the wave's exit criteria.

## Boundaries

Read-only. The script calls `databricks api get` only; nothing is created, granted or changed. It
never installs SAT — if the client wants SAT, their platform team installs it and you read its
tables. Credentials are the CLI's; never print or pass a token. The rule ideas are SAT's
(Databricks License — used with the Databricks Services); the code is this pack's.

## References

`references/sat-checks.json` (catalog: check id, SAT numeric id, severity, scope, doc links) ·
`scripts/posture.py --help` · `scripts/test_posture.py` (offline self-check) ·
`../discovery-intake/references/run-layout.md` (finding and readiness schemas).
