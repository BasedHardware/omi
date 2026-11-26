# v3 size quarantine (SCA-2918)

Under `afab9560`, 12 owners stayed parked on `document_too_large`. The transcript cap engaged, but
the oversize documents were ones it doesn't measure:

- finished derived rows near 1 MiB from recording-alias `legacy_ids` (up to 128 per file);
- transcript-heavy rows that predate the cap;
- source recordings already at the limit.

`_oldest_pending` re-seeded the same recording every backoff, so one closure froze each owner's
backlog.

`CONVERSATIONS_V3_SIZE_QUARANTINE` (default on): a one-seed pass Firestore rejects for size records
every pending recording it loaded in the builder lease's `v3_size_quarantine` (all or nothing, at most
64), so seeds sharing that closure are set aside together.
- Closures still load quarantined rows, so claims are never filtered. Live seeding, the pass chain and the
  sweep skip them, and the next independent seed runs on the following wake.
- The lease's open window loads on every pass by itself. With one loaded, a pass quarantines only when
  Firestore names an oversize document outside that window.
- New quarantines record a degraded `omi_fallback_total` (component `conversations_v3`).

This change doesn't shrink any document. Rows bloated by alias `legacy_ids` stay quarantined until a
follow-up slims them. `/v1/sync/audio/{conversation_id}/{audio_file_id}` still resolves old client
handles through an alias's `legacy_ids` (`routers/sync.py`), so that follow-up needs a design for that
reader first.

Rollback: set the switch off on the builder runners; stored ids are then ignored.

Readback, as two numbers that are never added together:
- **owners recovering:** parked `document_too_large` owners whose park cleared and whose
  non-quarantined pending rows older than 1 h are draining;
- **work quarantined:** ids in `v3_size_quarantine`, owners holding any, and owners whose list is full.
  Quarantined work stays unrepaired until the oversize document is fixed.
