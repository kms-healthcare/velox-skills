CREATE PROCEDURE [dbo].[sp_Yearend_Inventory_Valuation] @fy INT
AS
BEGIN
    -- Runs once a year on Jan 2 (SQL Agent job JOB_YEAREND). Finance audit input.
    INSERT INTO dbo.FACT_YEAREND_INVENTORY (fy, sku, store_cd, qty_on_hand, valuation, calc_dt)
    SELECT @fy, p.sku, s.store_cd, SUM(t.qty) * -1, SUM(t.qty) * -1 * p.unit_cost, GETDATE()
    FROM dbo.STG_POS_TXN t JOIN dbo.DIM_PRODUCT p ON p.sku = t.sku JOIN dbo.DIM_STORE s ON s.store_cd = t.store_cd
    WHERE YEAR(t.txn_dt) = @fy
    GROUP BY p.sku, s.store_cd, p.unit_cost;
END
