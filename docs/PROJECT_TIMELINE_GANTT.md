# Nexus V2 POC, Testing, CDC, and Production Timeline

## Direct answer

A realistic timeline without major loopholes is:

| Track | Estimated Duration |
|---|---:|
| POC only | 2 to 3 weeks |
| Hardened UAT-ready version | 4 to 6 weeks |
| Production-ready with security, monitoring, delete reconciliation, replay, and rollback | 8 to 12 weeks |
| Production-ready including CDC/database replication integration | 10 to 16 weeks |

The timeline depends mostly on provider API behavior, final table complexity, CDC source access, and how many brands/entities must be onboarded in the first release.

## Plain-English justification

The S3/SQS/EC2 part is not the longest part.

The longer work is making sure the data rules are correct:

- which date field per brand/entity,
- what business key identifies each record,
- how to detect source deletes safely,
- how to avoid false deletes,
- how to replay failed batches,
- how to secure IAM, database, EC2, and secrets,
- how to validate CDC/replication without duplicate or orphan records.

## Gantt chart - POC and production plan

```mermaid
gantt
    title Nexus V2 ETL POC to Production Plan
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d

    section Planning and Design
    Finalize brand/entity rules                 :a1, 2026-07-01, 4d
    Confirm source API pagination and limits    :a2, after a1, 3d
    Confirm business keys per entity            :a3, after a1, 4d

    section Infrastructure POC
    Create S3, SQS, DLQ, IAM role               :b1, 2026-07-06, 3d
    Deploy EC2 worker and systemd               :b2, after b1, 2d
    Configure PostgreSQL schemas and roles       :b3, after b1, 3d

    section Pipeline POC
    API Dumper POC                              :c1, 2026-07-10, 5d
    S3 to SQS to worker test                    :c2, after b2, 2d
    Raw and staging load test                   :c3, after c2, 3d
    Final upsert POC                            :c4, after c3, 4d

    section Delete Reconciliation
    Dynamic entity_batch_rule implementation    :d1, 2026-07-17, 3d
    source_batch_keys implementation            :d2, after d1, 3d
    Delete history and soft-delete procedure    :d3, after d2, 4d
    Reactivation and replay testing             :d4, after d3, 3d

    section QA and Security
    S3/SQS/DLQ QA                               :e1, 2026-07-24, 3d
    Data QA and false-delete tests              :e2, after e1, 5d
    Security hardening and IAM review           :e3, after e1, 5d
    Monitoring and alerting                     :e4, after e2, 4d

    section CDC and Production
    CDC source assessment                       :f1, 2026-08-04, 5d
    CDC POC                                     :f2, after f1, 7d
    CDC reconciliation with ETL                 :f3, after f2, 7d
    UAT and parallel run                        :f4, after f3, 10d
    Production cutover                          :f5, after f4, 3d
```

## Phase-by-phase estimate

### Phase 1 - POC foundation: 2 to 3 weeks

Deliverables:

- S3 bucket
- SQS queue
- DLQ
- EC2 worker
- raw load
- staging load
- sample final upsert
- one brand/entity POC
- basic delete-before-insert test

### Phase 2 - Hardened pipeline: 4 to 6 weeks

Deliverables:

- dynamic `etl.entity_batch_rule`
- rolling 3-day lookback
- source-delete history
- soft-delete final rows
- reactivation
- backfill/replay
- DLQ handling
- audit tables
- operational logs

### Phase 3 - Production readiness: 8 to 12 weeks

Deliverables:

- IAM least privilege
- database role hardening
- secret management
- CloudWatch alerts
- CloudTrail
- failure runbook
- UAT data validation
- performance tests
- retention policy
- disaster recovery procedure

### Phase 4 - CDC/replication included: 10 to 16 weeks

Deliverables:

- CDC source assessment
- CDC tool selection
- CDC POC
- CDC-to-ETL merge rules
- duplicate handling between API pull and CDC
- replay strategy
- reconciliation report
- production parallel run

## Recommended project answer for management

For a safe production-grade implementation, the realistic estimate is 8 to 12 weeks for the ETL pipeline, including security, monitoring, delete reconciliation, replay, and production readiness.

If CDC/database replication is included, the safer estimate is 10 to 16 weeks because CDC requires additional source access, replication permissions, validation, and duplicate-prevention rules.
