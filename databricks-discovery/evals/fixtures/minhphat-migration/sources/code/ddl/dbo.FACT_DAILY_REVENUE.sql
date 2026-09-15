CREATE TABLE [dbo].[FACT_DAILY_REVENUE] (
    rev_dt DATE,
    store_cd VARCHAR(10),
    gross_amt DECIMAL(18,2),
    return_amt DECIMAL(18,2),
    net_amt DECIMAL(18,2),
    txn_cnt INT,
    calc_dt DATETIME
);
