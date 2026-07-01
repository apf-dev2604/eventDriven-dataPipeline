# Cost Estimator

Replace assumptions with real values.

Assumption example:
- 4 entities
- pull every 5 minutes
- 288 files/day/entity
- 1,152 files/day total
- 34,560 files/month
- average compressed file size = replace with actual MB

Formulas:
- S3 storage = monthly_storage_gb * S3 Standard price per GB-month
- S3 PUT = files_per_month / 1000 * PUT price per 1,000
- S3 GET = processed_files_per_month / 1000 * GET price per 1,000
- SQS = total_sqs_requests / 1,000,000 * SQS standard request price
- EC2 = hourly_price * 24 * 30
- EBS = gp3_gb * gp3 price per GB-month
