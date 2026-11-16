# CLAUDE.md

Guidance for agents working in **velox-skills**, the Claude Code plugin marketplace behind Velox's
Databricks work. The skills run against real client projects and workspaces, so the rules below
are about not harming a client while improving the pack. See `README.md` for what each skill does.

## Client workspaces

- Never run a write against a client workspace without the person's explicit approval for THAT
  command: `bundle deploy/destroy`, `api post/put/patch/delete`, `jobs run-now`, any SQL that is not
  a SELECT, grants, secret scopes, settings.
- The default identity is the client's read-only service principal profile. Pass `--profile`
  every time; never pick a profile silently.
- Never print or read a credential: `databricks auth token`, `auth env`,
  `auth describe --sensitive`, `secrets get-secret`.
- Skills read the workspace GET-only (`security-posture`) or not at all (`cost-performance` reads
  saved files). Keep it that way: a skill that needs a write hands off to the person with options
  (`discovery-intake` § "Blocked mid-run").

## Per-client configuration

- Nothing client-specific in `skills/`, `references/` or `scripts/`: no client or partner names,
  workspace hosts, catalog names, account ids. It lives in the client's project folder
  (`registers/`, `runs/`), never in this repo.
- Fixtures and tests use synthetic names only (`minhphat-migration` is synthetic). Never copy a
  client's file into `evals/fixtures/`.
- The agent writes into `runs/<date>_run-NN/`; only a human merges into `registers/`.

## Data leaving the client

- Metadata and aggregates may go to the model. Row-level values, documents and transcripts go
  only as far as the client has agreed; when unsure, ask before reading them into the prompt.
- Never paste client data into a commit, an eval, an issue or a PR body.

## Verifying output

- Numbers in a deliverable come from a script or a saved file with a locator, never from the
  model (`posture.py` scores, `build_deliverables.py` builds the report and workbook).
- Every statement carries a locator and a `stated` / `inferred` label; records pass
  `write_records.py` before they count.
- Converted SQL is not "converted" until it parses (sqlglot, Databricks dialect) and a test on
  real or fixture data passes.
- Before saying a change is done:
  ```bash
  for d in databricks-discovery/skills/*/scripts; do (cd "$d" && python -m pytest -q); done
  ```
  (`assessment-synthesis` needs `openpyxl`.) A change to a `SKILL.md` also re-runs the matching
  case in `databricks-discovery/evals/evals.json`. Report failures verbatim.

## Versioning

- Bump `databricks-discovery/.claude-plugin/plugin.json` `version` with every change to a skill,
  and a skill's own `metadata.version` when its behaviour changes.
- Skills are written in English; artifacts follow the user's working language.
