CREATE TABLE [dbo].[STG_SAP_PO] (
    po_id VARCHAR(20),
    vendor_id VARCHAR(20),
    po_dt DATE,
    amount DECIMAL(18,2),
    load_dt DATETIME
);
