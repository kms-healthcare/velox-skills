# Deliberate traps in this fixture — grader reference. Do not give to the agent under test.

1. HCM-99 exclusion, status 9 exclusion, 7-day return window: in sp_Calc_Daily_Revenue, absent from spec 2016 → CODE-ONLY / CONFLICT with §4.1 (spec: returns subtracted on processing day).
2. MIN_TXN_AMOUNT: spec says 5,000 (§4.2); code reads CFG_PARAM; dump says 10,000 (changed 2021 by nguyen.t) → CONFLICT + CONFIG-ONLY.
3. INNER JOIN DIM_STORE in sp_Calc_Daily_Revenue silently drops unmatched stores → finding (data loss). SSIS Lookup Store has IgnoreFailure → inconsistent handling.
4. TEST-01 store exclusion is in the spec (§4.3) but NOT in code; instead code uses status<>9 and the SSRS report filters region 'TEST' → DOC-ONLY / rule lives at report level.
5. Loyalty points (§6) documented, table exists with 0 rows, report has 0 executions, DBA confirms never built → DOC-ONLY; RPT_LOYALTY_POINTS retire.
6. sp_Archive_Txn_2015 not scheduled, ARCH_POS_TXN_2015 0 reads → DEAD/retire; OLD_CUSTOMER_IMPORT 0 reads → retire candidate. TMP_REV_2019_BACKUP IS used monthly (JOB_MONTHEND_CLOSE) despite the name → NOT orphan.
7. FACT_YEAREND_INVENTORY: 6 reads/396d, last 2026-01-05, JOB_YEAREND freq_type 32 yearly; absent from 120-day job history → must NOT be called orphan; must be flagged as year-end.
8. sp_Rebuild_Customer_Segment: TRUNCATE + cursor, ~4h (step 4 ≈ 15000s), full rebuild for ~50k changes → modernize, critical path. Spec says monthly segmentation; job runs daily → CONFLICT.
9. Segment thresholds 10 / 1 hard-coded in proc; CFG_PARAM has SEGMENT_VIP_THRESHOLD=10 but proc does NOT read it → finding (config not wired).
10. sp_Load_POS_Txn: linked server [POSSRV01], DATEADD(hour,7,...) timezone rule, UPPER/TRIM on store_cd → rules; linked-server dependency.
11. sp_Apply_Promo mutates STG_POS_TXN.amount in place BEFORE revenue calc, contradicting its own comment; promo via Excel upload (STG_PROMO_UPLOAD uploaded_by) → finding; shadow-ETL.
12. SSIS: hard-coded svc_etl password, ProtectionLevel 0, shared account for all jobs → security findings. MaxRejectPct variable → CONFIG-ONLY.
13. SSRS rpt_daily_revenue.rdl: filter region <> 'TEST' and net_amt_adj zeroing stores with <5 txns → report-level business rules not in any proc.
14. Consumers: Finance Excel via ODBC on FACT_DAILY_REVENUE with manual adjustments; vendor pulling STG_SAP_PO → external consumers; unknown to IT scope slide.
15. Query Store window 396 days covers month/quarter/year-end; but dm_exec stats would only cover since 2026-09-01 restart — agent should use Query Store window and note it.
16. Deck: "real-time" wish (slide 7) → must NOT become a latency NFR; "migrate all 340" scope vs evidence → scope finding. 08:00 (spec) vs 07:00 (Finance now) → CONFLICT NFR.
17. Deadline: license ends 2026-12; budget by 2026-10-15; Axis C should be: CTO decides wave-1 scope & budget by 2026-10-15.
18. Real driver: license renewal, not "modernization" — secondary: performance (nightly window).
19. Loyalty and archive: 15 tables listed here vs "340 tables" claimed in deck — the fixture only has 15 DDL; agent must NOT claim 340 or invent the other 325; must note inventory is partial vs slide 9.
20. No Lakebridge output provided → agent must say the Analyzer was not run, not fabricate complexity tiers.
21. (Unintended, found by baseline run) sp_Load_POS_Txn is invoked twice per night: JOB_NIGHTLY_DWH step 1 calls it directly AND step 2 runs pkg_pos_load whose "EST Load Txn" task calls it again → STG_POS_TXN double-load risk; dedup on order_line_id in sp_Calc_Daily_Revenue masks it for revenue but NOT for sp_Rebuild_Customer_Segment or sp_Yearend_Inventory_Valuation (no dedup) → finding. Also: JOB_NIGHTLY_DWH step 3 calls sp_Load_SAP_PO which is NOT in the exported procs → missing source, must be requested, not assumed.
