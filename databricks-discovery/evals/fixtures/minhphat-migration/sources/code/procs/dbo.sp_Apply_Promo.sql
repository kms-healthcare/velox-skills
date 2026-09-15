CREATE PROCEDURE [dbo].[sp_Apply_Promo] @rev_dt DATE
AS
BEGIN
    -- Promo discounts uploaded by Marketing via Excel (STG_PROMO_UPLOAD). Applied to gross before revenue calc? No — applied to report only. See rpt_daily_revenue.rdl.
    UPDATE t SET amount = amount * (1 - pr.discount_pct/100.0)
    FROM dbo.STG_POS_TXN t JOIN dbo.STG_PROMO_UPLOAD pr ON pr.sku = t.sku
    WHERE CAST(t.txn_dt AS DATE) = @rev_dt AND @rev_dt BETWEEN pr.start_dt AND pr.end_dt;
END
