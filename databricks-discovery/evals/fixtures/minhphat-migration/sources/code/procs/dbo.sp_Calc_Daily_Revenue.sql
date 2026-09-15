CREATE PROCEDURE [dbo].[sp_Calc_Daily_Revenue] @rev_dt DATE
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @min_amt DECIMAL(18,2);
    SELECT @min_amt = CAST(param_val AS DECIMAL(18,2)) FROM dbo.CFG_PARAM WHERE param_key = 'MIN_TXN_AMOUNT';

    DELETE FROM dbo.FACT_DAILY_REVENUE WHERE rev_dt = @rev_dt;

    ;WITH dedup AS (
        SELECT t.*, ROW_NUMBER() OVER (PARTITION BY t.order_line_id ORDER BY t.load_dt DESC) AS rn
        FROM dbo.STG_POS_TXN t
        WHERE CAST(t.txn_dt AS DATE) = @rev_dt
    ),
    valid AS (
        SELECT d.*
        FROM dedup d
        WHERE d.rn = 1
          AND d.status <> 9                 -- test transactions
          AND d.store_cd <> 'HCM-99'        -- central warehouse, not a store (2019 reorg)
          AND d.amount >= @min_amt
    ),
    early_returns AS (
        SELECT r.txn_id, SUM(r.amount) AS return_amt
        FROM dbo.STG_POS_RETURN r
        JOIN valid v ON v.txn_id = r.txn_id
        WHERE DATEDIFF(day, v.txn_dt, r.return_dt) <= 7
        GROUP BY r.txn_id
    )
    INSERT INTO dbo.FACT_DAILY_REVENUE (rev_dt, store_cd, gross_amt, return_amt, net_amt, txn_cnt, calc_dt)
    SELECT @rev_dt, s.store_cd,
           SUM(v.amount), SUM(ISNULL(er.return_amt, 0)),
           SUM(v.amount) - SUM(ISNULL(er.return_amt, 0)),
           COUNT(*), GETDATE()
    FROM valid v
    INNER JOIN dbo.DIM_STORE s ON s.store_cd = v.store_cd     -- unmatched stores silently dropped
    LEFT JOIN early_returns er ON er.txn_id = v.txn_id
    GROUP BY s.store_cd;
END
