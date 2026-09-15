CREATE TABLE [dbo].[FACT_CUSTOMER_SEGMENT] (
    cust_id INT,
    segment_cd VARCHAR(5),
    score DECIMAL(9,4),
    calc_dt DATETIME
);
