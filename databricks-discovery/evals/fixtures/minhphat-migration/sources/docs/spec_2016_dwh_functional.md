# Minh Phát Retail — Data Warehouse Functional Specification (v1.2, March 2016)

## 4. Revenue reporting
### 4.1 Daily revenue
Daily revenue is the sum of all sales transactions for the day, per store. Returns are subtracted
from the day on which the return is processed.
### 4.2 Minimum transaction
Transactions below 5,000 VND are excluded as rounding artefacts.
### 4.3 Test data
The test store `TEST-01` is excluded from all reports.

## 5. Customer segmentation
Customers are segmented monthly into VIP / GOLD / STANDARD based on 12-month spend. Segments are
refreshed on the first day of each month.

## 6. Loyalty points
Loyalty points accrue at 1 point per 10,000 VND net spend and are reported in the Loyalty Points
report available to Marketing. (Table RPT_LOYALTY_POINTS.)

## 7. Non-functional
Reports must be available by 08:00 each business day.
