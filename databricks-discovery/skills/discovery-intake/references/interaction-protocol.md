# Interaction protocol — the skill runs in a chat, not in a batch job

These skills execute inside an agent conversation. Everything the agent cannot decide alone —
access, approval, a business owner's answer, a new integration — arrives through that conversation
or not at all. This file is the contract for it. It binds all four skills.

One principle: **the agent never blocks the whole turn on an answer, and never acts past a gate
without one.** Deliver everything that does not depend on the answer, then ask.

## 1. The shape of every reply

Four parts, ≤ ~300 words total, in this order. Nothing else.

1. **What I concluded** — one or two sentences. Not a summary of the report.
2. **What I wrote** — paths only (`runs/<run>/…`, deliverables). The files are the deliverable.
3. **What I need** — ≤ 5 blocking questions, or an access/approval request (§3, §4), or nothing.
4. **What I deliberately did not conclude** — and which evidence would let me.

Findings, rule tables and inventories go in the registers where they carry a locator and can be
merged. Repeated in chat they are read once and lost, and they cost a third copy of the output.

## 2. Actions that stop and ask first

Do the work up to the gate, then ask in the same turn. Never assume approval from silence, from a
general "go ahead" given earlier for something else, or from the user having asked for the outcome.

| Action | Ask because | Default when unanswered |
|---|---|---|
| Connecting to any client system — database, workspace, API, file share | It is the client's system, not ours, even read-only | Stay on the files in hand; mark the conclusions that need it ❌ in `sufficiency.md` |
| Running a scanner on a live system — Lakebridge Analyzer, SAT, UCX, a query-log export | It puts load on a production system and usually needs a credential | Ask for the scanner **output** instead; it is often cheaper for the client to run it |
| Reading row data rather than metadata and statistics | Client data leaves the client's control | Metadata and aggregates only |
| Egress beyond metadata, statistics and ≤ 20 masked sample rows | The cap in `run-layout.md` is the standing permission; more is a new decision | Do not send it |
| Writing into `registers/` | Registers are the source of truth; a human merges them after reading `review.md` | Write into `runs/<run>/` and say what is ready to merge |
| Overwriting a deliverable that has already gone to the client | Someone is quoting the old version | Write beside it with a new name and say both exist |
| Sending anything to a person outside this chat | The email drafts in the workbook are drafts | They stay drafts; the user sends them |
| Installing tooling, starting paid compute, or any spend | Not ours to spend | Say what it would cost and what it buys |
| Changing the decision the report serves, or the scope of the run | It invalidates `sufficiency.md` and possibly the whole assessment | Keep the recorded decision; raise a finding about the drift |

Every granted gate is recorded in `manifest.json` under `approvals[]` — `{what, asked_at,
granted_by, granted_at, scope, expires}`. **Nothing that needed approval happens without a row.**

## 3. Asking for access or a new integration

One block, not a paragraph. Eight lines, every one of them load-bearing:

```
Access needed:  read-only on <system>, <specific objects or scope>
Unlocks:        <the conclusion in sufficiency.md that is ❌ or ⚠️ today>
Minimum grant:  <the least privilege that works — name it exactly>
Identity:       service principal + OAuth M2M (never a personal PAT)
Who grants:     <role, and the name if known>
Lead time:      <realistic; access is usually the longest item in the project>
Meanwhile:      <what I am doing that does not depend on it>
If never:       <the conclusion that stays out of the report, and the risk of shipping without it>
```

Known integrations and what to ask for:

| Integration | Ask for | Minimum grant |
|---|---|---|
| Databricks workspace | service principal + OAuth M2M; managed MCP if available | read on system tables, `USE CATALOG`, no data grants |
| Source database (SQL Server, Oracle, Teradata…) | read-only login, or an export the DBA runs | catalog views + query-log export; row access only if a conclusion needs it |
| Query log / usage export | the export, not the connection | ≥ 90 days covering a month-end and a quarter-end; state the window |
| Lakebridge Analyzer | the client's own run, or a code export we analyse offline | the full script export; partial exports give a partial inventory, not a smaller one |
| SAT | the existing report | nothing — read its output, do not rebuild its checks |
| Jira / Confluence / ticket system | search access, or an export of the relevant space | read on the named space or project |
| File share / drop folder | a copy, or a path plus read access | the artifacts named in `source_request.md` |

The first line of `source_request.md` is always the access request. If the same access has been
pending for two turns, say so plainly and put a date on it — a stalled access request is a project
risk, not an administrative detail.

## 4. Asking questions well

- **≤ 5 per turn**, ordered by `impact_if_wrong`, each with *why · recommended default · what breaks
  if wrong · who can answer*. The rest stay in `open_questions.jsonl` and reach people through the
  workbook's *Open Questions* tab, which carries an email draft per row.
- **Never ask what the evidence already answers.** Read first. A question the sources settle is an
  interrogation the user pays for twice.
- **Never reply "give me more information."** Classify provisionally, deliver the source request,
  attach the questions.
- **Group by the person who answers**, not by topic. One person, one message.
- **Never re-ask an answered question.** Before asking, read `open_questions.jsonl` for
  `status: answered` and for defaults already applied.
- Questions reach a business owner unchanged as report §2 — write them in the business register
  (`../../assessment-synthesis/references/plain-language.md`).

## 5. Recording what comes back

An answer is evidence and is written like evidence. On `open_questions`: `answer`, `answered_by`,
`answered_at`, `status: answered`, and `answer_kind`:

| `answer_kind` | Means | May it settle the record? |
|---|---|---|
| `client-confirmed` | the named owner in `ask` decided, and there is a locator — email, meeting note, ticket | Yes. Only this may set `owner_agreed: true` or move a rule to `VERIFIED` |
| `user-relayed` | the engineer in this chat said it | No. It is evidence of their belief; it raises confidence and keeps the question open against the named owner |
| `assumed-default` | nobody answered by the date; the recorded default applies | No. The question stays open in the report and the assumption is visible |

This distinction is the whole point. An engineer saying "yes that rule is right" in chat is not the
business owner signing it, and a report that treats the two as equal is the failure mode this skill
pack exists to prevent.

Applying a default is an event, never a silence: say it in the turn, set `answer_kind`, keep the
row in §2, and name what changes if it turns out wrong.

## 6. Long analyses — checkpoints and interrupts

Before reading a large set (say 20+ sources), state the plan in one line: order, batch size, what
each batch returns. Then deliver batch by batch — a partial register a human can merge beats a
complete one that arrives after the budget is gone.

**Checkpoint** (finish the batch, then ask): the record budget is about to be exceeded · a source
turns out to be something other than it was labelled · an assumption that would change the reading
of everything already done · the plan needs to change.

**Interrupt immediately** (stop, report, wait): a credential or secret found in client code · PII
where it was not expected · evidence that the decision date in `intake.md` cannot be met · anything
that would be negligent to sit on until the end of the batch.

## 7. Resuming a conversation

The registers are the memory, not the transcript. On resuming: read `registers/` and
`open_questions.jsonl`, state in one line what changed since the last turn and what is still
blocked, then continue. Do not replay earlier conclusions and do not re-ask answered questions.
