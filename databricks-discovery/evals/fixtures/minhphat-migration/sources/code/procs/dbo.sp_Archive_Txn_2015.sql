CREATE PROCEDURE [dbo].[sp_Archive_Txn_2015]
AS
BEGIN
    -- One-off archive from the 2015 platform migration. Not scheduled anywhere.
    INSERT INTO dbo.ARCH_POS_TXN_2015 SELECT txn_id, store_cd, txn_dt, amount FROM dbo.STG_POS_TXN WHERE txn_dt < '2016-01-01';
END
