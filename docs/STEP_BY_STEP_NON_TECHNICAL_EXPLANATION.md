# Nexus V2 Step-by-Step Explanation for Non-Technical Readers

## Simple analogy

Think of the provider system as the main store inventory.

Our system is the branch inventory copy.

Every 5 minutes, we ask the main store: "What items currently exist for this batch window?"

If the main store had 10 items before and now only has 9, we do not blindly erase the missing item. First, we check that the main store gave us the complete list. If the list is complete, we copy the old item record into an archive folder, then mark it as removed from our active inventory.

That is the purpose of source-delete reconciliation.

## Plain workflow

1. The API Dumper runs every 5 minutes.
2. It checks the configuration to know which brand/entity to pull.
3. It checks which date field to use. This is dynamic. It can be createdDate, settledDate, transactionDate, updatedAt, or another provider field.
4. It pulls the source data from the provider API.
5. It writes the exact provider result into S3 as a compressed JSONL file.
6. S3 sends an event to SQS.
7. The EC2 worker reads the SQS message.
8. The worker downloads/streams the S3 file.
9. The raw loader saves the provider result into raw tables.
10. The adapter translates provider-specific fields into standard staging tables.
11. The adapter writes compact business keys into `staging.source_batch_keys`.
12. The stored procedure checks if the batch is complete and safe.
13. If safe, it compares current source keys against active final keys.
14. Any final key missing from the current source batch is copied to delete history.
15. The final row is soft-deleted, not physically erased.
16. Current source rows are inserted or updated into final.
17. If a previously deleted row appears again, it is reactivated.
18. Audit tables show what happened.

## Why this is safe

We do not delete from final just because a count is lower.

Count is only a warning.

The actual delete decision is based on a missing business key.

Example:

- Final has A, B, C, D.
- Source now has A, B, C.
- D is missing.
- If the source batch is complete, D is copied to history and marked source-deleted.

## Why this is faster

The system does not compare full JSON payloads.

It compares small keys such as:

```text
brand | platform | external_id
```

This is faster, easier to index, and easier to audit.

## Why this is dynamic

Different brands and entities can use different date fields.

Examples:

| Brand | Entity | Batch Date Field | Business Key |
|---|---|---|---|
| Inplay | gameTx | createdDate | brand + platform + externalId |
| Provider B | gameTx | settledDate | brand + platform + transactionId |
| Provider C | deposits | transactionDate | brand + platform + referenceId |
| Provider D | players | registeredDate | brand + username |

The rules are stored in `etl.entity_batch_rule`, so the pipeline does not need to hard-code one date field.

## Main justification

This design avoids the common loopholes:

- no false delete from partial API result,
- no hard delete without history,
- no date-field hard-coding,
- no full-table scan every 5 minutes,
- no final insert before delete reconciliation,
- no loss of audit trail,
- no orphan or ghost transaction in active final data.
