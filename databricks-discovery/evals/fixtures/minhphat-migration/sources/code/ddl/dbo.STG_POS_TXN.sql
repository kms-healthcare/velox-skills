CREATE TABLE [dbo].[STG_POS_TXN] (
    txn_id BIGINT,
    store_cd VARCHAR(10),
    txn_dt DATETIME,
    sku VARCHAR(20),
    qty INT,
    amount DECIMAL(18,2),
    status TINYINT,
    cust_id INT,
    order_line_id BIGINT,
    load_dt DATETIME
);
