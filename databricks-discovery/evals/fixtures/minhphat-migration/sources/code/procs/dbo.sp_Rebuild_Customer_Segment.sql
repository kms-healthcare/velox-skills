CREATE PROCEDURE [dbo].[sp_Rebuild_Customer_Segment]
AS
BEGIN
    SET NOCOUNT ON;
    TRUNCATE TABLE dbo.FACT_CUSTOMER_SEGMENT;   -- full rebuild nightly, ~8M customers
    DECLARE @cust_id INT, @score DECIMAL(9,4);
    DECLARE c CURSOR FOR SELECT cust_id FROM dbo.DIM_CUSTOMER;
    OPEN c; FETCH NEXT FROM c INTO @cust_id;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SELECT @score = SUM(amount) / 1000000.0
        FROM dbo.STG_POS_TXN WHERE cust_id = @cust_id AND txn_dt >= DATEADD(month, -12, GETDATE());
        INSERT INTO dbo.FACT_CUSTOMER_SEGMENT VALUES (@cust_id,
            CASE WHEN @score >= 10 THEN 'VIP' WHEN @score >= 1 THEN 'GOLD' ELSE 'STD' END, ISNULL(@score,0), GETDATE());
        FETCH NEXT FROM c INTO @cust_id;
    END
    CLOSE c; DEALLOCATE c;
END
