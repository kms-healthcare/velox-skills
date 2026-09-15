CREATE TABLE [dbo].[DIM_CUSTOMER] (
    cust_id INT,
    full_name NVARCHAR(200),
    cccd VARCHAR(12),
    phone VARCHAR(15),
    email VARCHAR(100),
    segment_cd VARCHAR(5),
    region_cd VARCHAR(5),
    updated_at DATETIME
);
