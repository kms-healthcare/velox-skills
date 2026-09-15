# Project type 7 — Data sharing

Load when Axis A = sharing. Data leaves the organisation's boundary — to partners, customers,
regulators, or a marketplace. Discovery is dominated by **legal and contractual constraints**;
the technical part (Delta Sharing) is the easy half.

## Recognising it

Signals: "share with partners", "customers want their data", "sell / monetize", "regulator needs
a feed", "Delta Sharing", "clean room", "we send CSVs over SFTP today".

## The real driver

> "Who is asking for the data, what will they do with it, and what happens if we share the wrong
> rows?"

## Decisions this assessment serves

Mechanism per partner (Delta Sharing open protocol vs Databricks-to-Databricks vs Clean Rooms vs
Marketplace); what may be shared at what grain; refresh SLA; revocation and audit model; egress
cost acceptance.

## Sources to request

### Required

| Source | Why | How |
|---|---|---|
| **Partner list** with their platform (Databricks or not), contact, and contract status | Mechanism and feasibility per partner | Business owner |
| **Datasets requested**, grain, columns, refresh expectation | What is actually being asked for vs what is safe | Partner requests; current SFTP/CSV extracts |
| **Legal / contractual constraints** per dataset: consent, PII, jurisdiction, retention, resale | Gating — nothing is shareable until this is answered | Legal / DPO; existing DPAs |
| **Current sharing method** and its problems | Baseline; the CSV-over-SFTP process usually hides transformations | Ops team |
| **Volume and read pattern** | Egress cost | Estimate from dataset size × partner refresh |

### Recommended

Data classification tags in UC; existing row/column masking; audit requirements; SLA penalties in
contracts; versioning expectations when schemas change.

## Databricks tools to use instead of building

**Delta Sharing** (open protocol to any client; D2D for Databricks recipients); **Clean Rooms**
for joint analysis without moving raw data; **Databricks Marketplace** for listings; **Unity
Catalog row filters and column masks** to share a governed subset; `system.access.audit` for who
accessed what.

## Conclusions the report must reach

1. **Share inventory**: dataset × partner × mechanism × refresh × legal status.
2. **Legal gating per dataset** — shareable / shareable after masking / not shareable — with the
   constraint cited.
3. **Grain and aggregation decisions** — event-level vs aggregate, and re-identification risk.
4. **Egress and compute cost** per partner.
5. **Operating model**: onboarding, revocation, schema change notice, audit.

## Evidence-sufficiency rules

| Cannot claim | Without |
|---|---|
| "Dataset D is shareable" | Legal review recorded with locator |
| "Partner P can consume via Delta Sharing" | Confirmation of their platform / client |
| "Cost is X" | Volume × refresh × partner count |
| "PII is excluded" | Column-level classification, not table names |

## Confirmation questions

- "Partner P asked for event-level data. What decision needs event level rather than daily aggregates?"
- "Who approves adding a column to a shared dataset, and how much notice do partners get?"
- "If a partner contract ends, how fast must access disappear, and who checks?"
- "Is this dataset's consent basis compatible with sharing to a third party?"

## What is routinely missed

Egress cost; partners not on Databricks; PII in "aggregated" data (small groups); schema
versioning; revocation process; hidden transformations in the current CSV extracts.

## Cost-risk flags

Sharing raw event-level data to many partners; per-partner bespoke extracts instead of one
governed share; Clean Rooms where a masked share would do.
