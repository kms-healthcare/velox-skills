CREATE TABLE [dbo].[STG_PROMO_UPLOAD] (
    promo_id VARCHAR(20),
    sku VARCHAR(20),
    discount_pct DECIMAL(5,2),
    start_dt DATE,
    end_dt DATE,
    uploaded_by VARCHAR(50)
);
