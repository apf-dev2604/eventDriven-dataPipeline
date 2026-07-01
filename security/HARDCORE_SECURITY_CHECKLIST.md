# Hardcore Security Checklist

## AWS

- Use EC2 IAM role, not static access keys.
- S3 Block Public Access must be ON.
- S3 server-side encryption must use KMS.
- SQS queue policy allows only the source S3 bucket to send messages.
- EC2 role can only read the raw bucket and receive/delete/change visibility on the SQS queue.
- Enable CloudTrail and CloudWatch logs.
- Store provider secrets in Secrets Manager or SSM Parameter Store.

## EC2

- Prefer SSM Session Manager; avoid public SSH.
- Run services under a non-root user.
- Restrict config file permissions to 600.
- Patch OS regularly.
- Use systemd Restart=always for worker.

## PostgreSQL

- No app superuser.
- Separate roles: nexus_dumper, nexus_worker, nexus_readonly, nexus_owner.
- Require TLS.
- Restrict DB security group to EC2 worker.
- Revoke PUBLIC schema access.
- Audit failed logins, DDL, and role changes.

## Logging

Allowed: batch_id, S3 key, counts, status, duration, error category. Do not log API tokens, DB passwords, authorization headers, or full PII payloads.
