CREATE TABLE [dbo].[FACT_YEAREND_INVENTORY] (
    fy INT,
    sku VARCHAR(20),
    store_cd VARCHAR(10),
    qty_on_hand INT,
    valuation DECIMAL(18,2),
    calc_dt DATETIME
);
