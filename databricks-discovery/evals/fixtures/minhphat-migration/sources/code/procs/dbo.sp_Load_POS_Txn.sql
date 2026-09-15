CREATE PROCEDURE [dbo].[sp_Load_POS_Txn] @load_dt DATE
AS
BEGIN
    -- Called by SSIS pkg_pos_load after file landing. Source: POS extract via linked server.
    INSERT INTO dbo.STG_POS_TXN (txn_id, store_cd, txn_dt, sku, qty, amount, status, cust_id, order_line_id, load_dt)
    SELECT txn_id, UPPER(LTRIM(RTRIM(store_cd))), DATEADD(hour, 7, txn_ts_utc), sku, qty, amount, status, cust_id, order_line_id, GETDATE()
    FROM [POSSRV01].[POSDB].[dbo].[v_txn_export]
    WHERE CAST(txn_ts_utc AS DATE) = @load_dt;
END
