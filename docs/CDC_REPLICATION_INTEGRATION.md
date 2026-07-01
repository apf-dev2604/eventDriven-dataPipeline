# CDC / Database Replication Integration Notes

## Purpose

CDC can improve near-real-time capture when the source database is available, but it must not create duplicates or bypass final validation.

## Recommended rule

CDC is another source input, not a replacement for validation.

CDC should still flow through:

```text
CDC extract
→ S3 or raw CDC table
→ staging
→ validation
→ delete reconciliation / final upsert
→ history/audit
```

## CDC and API together

If both API pull and CDC are active, the system needs a priority rule.

Recommended:

1. CDC captures low-latency inserts/updates/deletes.
2. API createdDate snapshot remains the reconciliation proof.
3. Final table uses idempotent business keys.
4. Duplicate records are ignored or updated based on source event time.
5. CDC deletes can mark source_deleted faster, but snapshot reconciliation still verifies correctness.

## CDC delete handling

If CDC provides a delete event, it is stronger than missing-from-snapshot.

Flow:

1. CDC delete event arrives.
2. Write CDC event to raw.
3. Write old final row to delete history.
4. Mark final row as source_deleted.
5. Store delete reason = `cdc_delete_event`.

## CDC project risk

CDC needs additional permissions and deeper DBA/security review. This is why the production estimate increases from 8-12 weeks to 10-16 weeks when CDC is included.
