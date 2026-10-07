---
name: security-posture
description: "Score a Databricks workspace's security posture against the Security Analysis Tool (SAT) check catalog - read-only, with every check passed, failed or reported as not assessed and why. Reads the live workspace through the Databricks CLI (GET only), imports SAT's own results when the client already runs SAT, and checks Terraform / bundle / grant SQL when there is no workspace yet. Writes security findings and the security readiness score into the discovery run. Use when asked for the security posture, a SAT-style check, the security section of the assessment, or a before/after security comparison of a migration. Never installs SAT or changes a setting."
compatibility: "Python 3.9+, stdlib only. Live mode needs the Databricks CLI signed in to the workspace (a read-only service principal by default)."
metadata:
  version: "0.2.2"
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
| The client's admin, by file | `posture.py bundle` → they run it → `--from-posture posture.json` | `workspace` | the person chose it (below); only what the admin observed live counts |

Pass them together in one run; a check takes its answer from the live workspace first, then SAT,
then the code — with one exception: a live read of an UNSET setting is an assumption about the
platform default, and SAT's row is an observation, so SAT wins there (measured 2026-10-05: DP-13
unset → assumed off, SAT saw the DBFS browser on). Where both answered and disagree, the live read
stands and the check carries `sat_verdict`; `posture.json` lists them in `sat_disagreements` and
the run prints them — review those first. Measured on the same workspace: 37 overlapping checks,
34 agree, SAT wrong on two (GOV-34 fails on state `MANAGED` though its own message allows it;
GOV-20 fails with no detail where the account API answers nothing on this tier). SAT lifted
coverage from 60% to 94%: the 25 checks it added are the account-level and compute ones. **Code alone never scores** — it finds gaps, it cannot see the posture
(`assessment-synthesis` refuses a security score on `basis: code`).

`scripts/posture.py` is relative to the `directory` `load_skill` returned for THIS skill — run it
as `python3 "<directory>/scripts/posture.py" …` from the project root. If the shell cannot read or
run it (`Operation not permitted`, an empty `ls`), that is a Velox sandbox gap: report it in one
line with the path, leave `RDY-security` unscored with `needs: "posture.py could not run"`, and
**never copy a score from a SAT dashboard or write one by hand** — measured 2026-10-06, an agent
did exactly that and the report carried a number nobody could reproduce.

```
python3 "<directory>/scripts/posture.py" run --out discovery/<project>/runs/<date>_run-NN \
  --workspace --profile <profile> [--sat-results sat-rows.json] [--iac <repo>] \
  [--cloud aws|azure|gcp] [--allowed-regions '^eu-|europe']
python3 "<directory>/scripts/posture.py" catalog      # what each check id is and how it is evaluated here
```

`--allowed-regions` comes from a residency requirement (`requirements.jsonl`, e.g. GDPR transfers)
— never from your own assumption. Without one, `VX-RES-1` stays not assessed.

## Who reads the workspace — run first, then offer the person a choice

A read-only identity cannot see most of the posture: workspace settings, tokens and init scripts
answer "Forbidden" to anyone but a workspace admin, and Databricks has no read-only admin role.
Measured on a Free Edition workspace: a read-only service principal covered 19% of the catalog's
weight (not scored), the same run as an admin 60%. So:

1. **Always run first with the identity the session is bound to** (`--read-as service-principal`).
   Do not ask before this run. If `RDY-security` comes back scored, you are done.
2. **Not scored because of permission → ask, do not pick.** Use the session's question tool
   (Velox: `ask_user`) with these options, one marked recommended, each with what it costs the person:

| Option | What happens | Recommend when |
|---|---|---|
| **Use my own login for this step** | `posture.py identity --profile <theirs>` first; then `run --workspace --profile <theirs> --read-as user-login`. Everything else stays on the service principal. **Cost, in the person's words:** *you run `databricks auth login --host <host> --profile <p>` in your own terminal (a browser opens there), then confirm here* — the agent cannot open a browser (measured 2026-10-07: the option promised "a browser round-trip", the person did the sign-in by hand and clicked "Done — signed in"). When `identity` already shows a VALID login, the cost is nothing | **recommended only when** `identity --profile <p>` already shows a valid login **and** `is_admin: true` — typical for an internal or test workspace. Login expired or missing → recommend *make the SP admin briefly* or the *client bundle* instead and offer the sign-in as a non-recommended option. Hide it, with the reason, when the login is valid but not admin |
| **Ask the client to make the service principal an admin, briefly** | Write the two commands for the client (below) into the chat. When they say done, `identity` must show `is_admin: true`; then `run --workspace --read-as elevated-service-principal`; then ask them to remove it and run `verify-revoked` | a client workspace whose team will grant it for minutes |
| **The client's admin runs it and sends the file back** | `posture.py bundle --out <dir>` → a zip with `RUN.md`; the person sends it; their admin returns `posture.json`; `run --from-posture <file>` (provenance and sha256 go into the manifest) | the client will not grant admin to any identity Velox holds |
| **Skip — report it as not scored** | Nothing more runs; §7 says not scored and why; raise an open question to the client's workspace admin | the person does not want to spend the round-trip now |

Never run the person's own login, or ask a client for admin, without that answer. A choice they
did not make is not theirs to defend to the client.

**The temporary grant, for the client** (replace the ids; `groups list --filter 'displayName eq "admins"'` gives the group id):

```
databricks groups patch <admins-group-id> --json '{"schemas":["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations":[{"op":"add","value":{"members":[{"value":"<service-principal-id>"}]}}]}'
# …and afterwards
databricks groups patch <admins-group-id> --json '{"schemas":["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations":[{"op":"remove","path":"members[value eq \"<service-principal-id>\"]"}]}'
```

3. **Before generating the report, after a temporary grant:** `posture.py verify-revoked --run
   <run dir>`. Still an admin → it records `FND-SEC-VX-ID-1` (high: "the assessment service
   principal still holds workspace admin") and you tell the person in chat; the report is **not
   blocked** — the finding goes through review like any other, and a reviewer who knows the client
   kept the grant on purpose rejects it with that reason. Removed → the readiness rationale records
   when it was checked.

`readiness.rationale` always names who read ("Read as eurostream-ci (the assessment service
principal, temporarily a workspace admin)…"), so report §7 shows on whose eyes the score rests.

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

The findings are `extracted`; they appear in the DRAFT report, and a person accepts or rejects each one before it reaches the final.
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
