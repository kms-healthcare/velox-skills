# workspace-posture — graded fixture for `security-posture`

Question: on a real workspace, does `security-posture` find the misconfigurations we know are
there, without inventing others? The answer key was locked before the first graded run.

1. A person plants two issues: `./plant.sh plant [profile]` (P-1 broad grant, P-2 job ACL). The
   agent never runs this — it changes the workspace.
2. Run the skill: `python3 ../../../skills/security-posture/scripts/posture.py run --workspace
   --profile <p> --allowed-regions '^eu-' --out <dir>`.
3. Grade: `python3 grade.py <dir>/posture.json` → recall over `expected_fail`, precision over
   every reported failure.
4. `./plant.sh unplant [profile]` afterwards.

Baseline before planting (2026-10-05, Free Edition workspace, AWS us-east-2): recall 13/15 (the
two misses are the unplanted P-1, P-2), precision 13/14 — the extra is `GOV-21`, SAT's metastore
owner rule firing on a Databricks-managed metastore.

Graded run with the plants in place (2026-10-05, live admin read + SAT 0.9.0 rows): **recall 31/31,
precision 31/33** — both planted issues found with their locators (`schema eurostream.gold: account
users ['ALL_PRIVILEGES']`; `eurostream_fraud: users` CAN_MANAGE). The two extras: `GOV-21` (SAT's
metastore-owner rule on a managed metastore — a reviewer rejects it) and `DP-13` (now in the key).
SAT's rows predated the plant, so `GOV-45` showed up in `sat_disagreements` with the live read
standing — the fresher observation wins, which is the point of running both.
