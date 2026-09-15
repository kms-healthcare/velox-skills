# Fixture: minhphat-migration

Synthetic legacy SQL Server DW for testing the databricks-discovery skill pack on a migration-type
project. Everything under `sources/` is what the agent receives. `TRAPS.md` is for graders only.

Test prompt (Vietnamese, as a real engineer would type it):

> Khách hàng Minh Phát Retail muốn chuyển data warehouse SQL Server lên Databricks. Tôi có folder
> sources/ gồm DDL, stored proc, 1 package SSIS, 1 report SSRS, export SQL Agent, Query Store,
> SSRS log, row count, spec 2016, ghi chú kickoff và 1 transcript phỏng vấn DBA. Giúp tôi làm
> discovery & assessment: xác định loại project, kiểm tra input đủ chưa, trích requirements và
> business rule, và cho tôi bản nháp assessment với danh sách câu hỏi cần hỏi khách.
