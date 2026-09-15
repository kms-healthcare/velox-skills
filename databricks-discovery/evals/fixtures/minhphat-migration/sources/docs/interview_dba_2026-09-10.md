# Interview — Head DBA (Anh Tuấn), 2026-09-10, 45 min

[00:03:10] Tuấn: License for SQL Server Enterprise ends December 2026. That's the real deadline. Management calls it "modernization" but honestly it's the renewal quote.
[00:06:45] Tuấn: The nightly job is one chain, five steps, runs 01:00 to about 06:30. Step 4 — customer segments — is the killer, four hours, it rebuilds everything for 8 million customers when maybe 50 thousand changed.
[00:11:40] Tuấn: Finance wants Daily Revenue by 07:00 now, not 08:00. We miss it maybe twice a month.
[00:14:30] Tuấn: HCM-99 isn't a store, it's the central warehouse, so we take it out of revenue. Been that way since the 2019 reorg I think. Nobody wrote it down.
[00:17:05] Tuấn: The 7-day return window — that came from a Finance ticket in 2020, they said returns after a week go to a different GL account.
[00:21:00] Tuấn: The minimum amount is in CFG_PARAM. Someone raised it to 10,000 in 2021, I don't remember who asked.
[00:24:30] Interviewer: Who else reads the warehouse? Tuấn: Finance has an Excel with an ODBC connection straight to FACT_DAILY_REVENUE, they do their own adjustments in it before sending to the CFO. And there's some vendor pulling STG_SAP_PO nightly, I think for the procurement portal.
[00:29:10] Tuấn: Everything runs as svc_etl. Same account for 10 years. The password is in the SSIS packages.
[00:33:00] Tuấn: The 2015 archive stuff — nobody touched it since the migration from the old Oracle box. Loyalty points never got built, Marketing gave up in 2017.
[00:38:20] Tuấn: Year-end inventory runs January 2nd. Audit needs it. Don't let anyone tell you that table is unused.
[00:41:00] Tuấn: Customer table has CCCD and phone in clear text. Everyone with a login can read it. We know.
