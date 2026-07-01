# Deployment Request: IAM, Permissions, Network, and Access Needed

## Purpose

This document lists what must be requested from Cloud, Infrastructure, Security, DBA, and Network teams before deployment.

## AWS resources to request

### 1. S3 bucket

Request:

- One private S3 bucket for raw provider files.
- Block Public Access enabled.
- Versioning enabled if approved.
- Server-side encryption with KMS.
- Lifecycle policy for raw file retention.

Example bucket:

```text
nexus-v2-raw-prod
```

### 2. KMS key

Request:

- Customer-managed KMS key for S3 encryption.
- EC2 worker role can encrypt/decrypt.
- Cloud/security admin can administer key.

Example alias:

```text
alias/nexus-v2-raw-kms
```

### 3. SQS standard queue

Request:

- SQS queue for S3 ObjectCreated events.
- Visibility timeout: start with 15 minutes.
- Redrive policy to DLQ.

Example:

```text
nexus-v2-s3-events-prod
```

### 4. SQS DLQ

Request:

- Dead-letter queue for failed messages.
- Retention: 7 to 14 days.

Example:

```text
nexus-v2-s3-events-dlq-prod
```

### 5. S3 event notification

Request:

- S3 ObjectCreated notification to SQS.
- Prefix filter:

```text
raw/
```

Optional suffix:

```text
.jsonl.gz
```

### 6. EC2 instance or container host

Request:

- Linux EC2 instance for the worker.
- Private subnet preferred.
- No public SSH preferred.
- Use SSM Session Manager.
- IAM instance profile attached.
- CloudWatch Agent installed.

Minimum POC size:

```text
t3.small or t3.medium
```

Production size depends on volume.

### 7. Secrets Manager or SSM Parameter Store

Request secret storage for:

- database DSN/password,
- provider API credentials,
- optional webhook secrets,
- KMS key aliases,
- application config values.

## IAM permissions needed

### EC2 worker IAM role

The EC2 worker needs least-privilege access to:

S3:

```text
s3:GetObject
s3:ListBucket
s3:PutObject          only if worker/API dumper writes files
s3:GetBucketLocation
```

SQS:

```text
sqs:ReceiveMessage
sqs:DeleteMessage
sqs:ChangeMessageVisibility
sqs:GetQueueAttributes
```

CloudWatch Logs:

```text
logs:CreateLogGroup
logs:CreateLogStream
logs:PutLogEvents
```

KMS:

```text
kms:Decrypt
kms:Encrypt
kms:GenerateDataKey
```

Secrets Manager/SSM:

```text
secretsmanager:GetSecretValue
ssm:GetParameter
ssm:GetParameters
```

### S3 to SQS permission

The SQS queue policy must allow the S3 bucket to send messages to the queue.

Required action:

```text
sqs:SendMessage
```

Principal:

```text
s3.amazonaws.com
```

Condition:

```text
aws:SourceArn = arn:aws:s3:::nexus-v2-raw-prod
```

## Network permissions needed

### EC2 outbound

Allow EC2 worker outbound to:

- S3 endpoint,
- SQS endpoint,
- Secrets Manager or SSM,
- CloudWatch Logs,
- PostgreSQL database host,
- provider API endpoint if the API Dumper runs on the same EC2.

### Database inbound

Allow PostgreSQL inbound only from:

- EC2 worker security group,
- approved DBA/admin jump host if needed.

Port:

```text
5432
```

### Provider API allowlist

If provider requires IP allowlisting, request outbound NAT IP or fixed egress IP.

## Database permissions needed

Request DBA to create roles:

```text
nexus_owner
nexus_dumper
nexus_worker
nexus_readonly
```

Request schemas:

```text
etl
raw
staging
rejected
final_history
final_consolidated access as needed
```

Worker role needs:

- insert/select/update on raw,
- insert/select/update on staging,
- execute stored procedures in etl,
- insert/select/update on final_history,
- insert/select/update on required final_consolidated tables,
- select on lookup/player tables needed for validation.

Dumper role needs:

- select/update on api config/watermark,
- insert/update on batch_run/api_pull_run,
- select on reconciliation_scope.

Readonly role needs:

- select on final and final_history only.

## CDC/replication permissions to request

If CDC will be included, request separately because this is more sensitive.

### PostgreSQL source CDC

Possible requirements:

```text
wal_level = logical
replication slot permission
publication on source tables
REPLICATION role or equivalent
SELECT on replicated tables
```

### MySQL source CDC

Possible requirements:

```text
binlog enabled
ROW binlog format
replication user
REPLICATION SLAVE / REPLICATION CLIENT permissions
SELECT on source tables
server_id configured
```

### SQL Server source CDC

Possible requirements:

```text
CDC enabled on database
CDC enabled on required tables
SQL Agent enabled
read access to CDC change tables
least-privilege service account
```

### Oracle source CDC

Possible requirements:

```text
ARCHIVELOG mode
supplemental logging
LogMiner or GoldenGate permissions
SELECT_CATALOG_ROLE or narrower equivalent
SELECT on source tables
access to redo/archive logs depending on tool
```

## Production approval checklist

- [ ] S3 bucket approved.
- [ ] SQS and DLQ approved.
- [ ] S3 event notification approved.
- [ ] EC2 instance or container host approved.
- [ ] IAM role created and attached.
- [ ] KMS key created and policy approved.
- [ ] Secrets storage approved.
- [ ] Database roles created.
- [ ] Security groups/firewall opened only to required endpoints.
- [ ] Provider API egress/IP allowlist completed.
- [ ] CloudWatch/CloudTrail enabled.
- [ ] CDC permissions approved if CDC is included.
