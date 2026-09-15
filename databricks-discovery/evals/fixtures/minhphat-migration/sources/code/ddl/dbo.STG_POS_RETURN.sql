CREATE TABLE [dbo].[STG_POS_RETURN] (
    return_id BIGINT,
    txn_id BIGINT,
    return_dt DATETIME,
    amount DECIMAL(18,2),
    reason_cd VARCHAR(5),
    load_dt DATETIME
);
