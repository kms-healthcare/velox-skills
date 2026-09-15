CREATE TABLE [dbo].[DIM_STORE] (
    store_cd VARCHAR(10),
    store_name NVARCHAR(100),
    region_cd VARCHAR(5),
    is_active BIT,
    open_dt DATE,
    close_dt DATE
);
