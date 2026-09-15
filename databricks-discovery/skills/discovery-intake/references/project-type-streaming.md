# Project type 5 — Real-time / streaming

Load when Axis A = streaming. The single most important finding in this type is usually that
**real-time is not needed** — and the assessment must be willing to say so with evidence.

## Recognising it

Signals: "real-time", "near real-time", "within minutes", "Kafka / Event Hubs / Kinesis", "IoT",
"events", "we need to react immediately", "streaming".

## The real driver

> "What action is taken within N minutes of the data changing, and by whom or by what?"

No action within the window → the requirement is *fresh data before the next decision*, which is
batch. A human reading a dashboard is rarely a real-time consumer; an alert, a fraud block, a
dispatch system is.

## Decisions this assessment serves

Latency tier per use case (seconds / minutes / hourly / daily); architecture (Auto Loader
micro-batch vs Structured Streaming vs Lakeflow Declarative Pipelines streaming tables vs Zerobus);
whether to accept 24/7 compute cost; late-data and dedup policy.

## Sources to request

### Required

| Source | Why | How |
|---|---|---|
| **Consumer list with the action and its latency need** | Defines the tier; kills wish-list real-time | Interview each consumer; write "action within N minutes" or "none" |
| **Event sources**: topics, schemas, throughput (avg / peak), retention, partitioning, ordering guarantees | Sizing and feasibility | Broker admin; schema registry |
| **Late / out-of-order / duplicate profile** — measured | Determines watermark, dedup key, restatement policy | Sample a day of events; compute `ingest_ts − event_ts` percentiles |
| **Existing batch pipelines for the same data** | What real-time replaces or duplicates | Job inventory |
| **Downstream**: dashboards, alerts, apps, their refresh behaviour | Whether anything actually consumes at the produced latency | BI / app owners |
| **24/7 cost tolerance** | Streaming compute never stops | Sponsor |

### Recommended

Schema-evolution history of the events; replay requirements (how far back); exactly-once needs;
SLA for end-to-end latency; peak calendars.

## Databricks tools to use instead of building

**Lakeflow Declarative Pipelines** streaming tables with expectations; **Auto Loader** for file
streams; **Zerobus Ingest** for direct event ingestion; **AUTO CDC** (ex-`APPLY CHANGES`) with
`SEQUENCE BY` for late and out-of-order data; **Lakeflow Connect** for CDC from databases.

## Conclusions the report must reach

1. **Latency tier per use case**, with the action that justifies it — most land in "15-minute
   micro-batch" or "daily".
2. **Throughput and volume** measured, with peaks.
3. **Late-data policy**: watermark, restatement window, what happens to events older than the window.
4. **Dedup and ordering requirements** per source.
5. **Cost comparison**: continuous vs triggered / scheduled for the same result.
6. **What the existing batch pipeline already covers**.

## Evidence-sufficiency rules

| Cannot claim | Without |
|---|---|
| A latency requirement | A named action within the window |
| Sizing | Measured peak throughput |
| "Exactly-once is required" | A consumer that breaks on duplicates, identified |
| Watermark | Measured late-arrival percentiles |

## Confirmation questions

- "In the 5 minutes after this event arrives, what happens differently?"
- "What is peak events/second, and on which day of the year?"
- "Events arrive up to 9 days late at p99 (locator). Restate, drop, or quarantine?"
- "Is anyone reading this more than once a day today?"

## What is routinely missed

Late-arriving data; at-least-once duplicates; schema drift in events; timezone in event timestamps;
the always-on cost; the dashboard that refreshes hourly anyway.

## Cost-risk flags

Continuous pipelines for hourly consumption; one big stream for all use cases; always-on warehouse
for a "real-time" dashboard viewed at 09:00.
