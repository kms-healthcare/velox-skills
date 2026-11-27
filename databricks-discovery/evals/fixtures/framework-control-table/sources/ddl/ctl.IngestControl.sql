-- Control table of the copy framework: one row per flow (exported from dwpool01).
CREATE TABLE [ctl].[IngestControl]
(
    [FlowId]           INT            NOT NULL,
    [FlowName]         NVARCHAR(100)  NOT NULL,
    [SourceSystem]     NVARCHAR(20)   NOT NULL,
    [SourceConnection] NVARCHAR(400)  NULL,      -- from the first version of the framework
    [SourceQuery]      NVARCHAR(4000) NOT NULL,
    [SinkSchema]       NVARCHAR(50)   NOT NULL,
    [SinkTable]        NVARCHAR(100)  NOT NULL,
    [TargetTable_Old]  NVARCHAR(100)  NULL,      -- staging table name before the lake
    [Frequency]        CHAR(1)        NOT NULL,  -- H = hourly, D = daily
    [IsEnabled]        BIT            NOT NULL
)
WITH (DISTRIBUTION = REPLICATE, HEAP);
