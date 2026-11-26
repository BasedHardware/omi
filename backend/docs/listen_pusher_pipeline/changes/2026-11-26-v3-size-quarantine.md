# v3 size quarantine (SCA-2918)

Under `afab9560`, 12 owners stayed parked on `document_too_large`. The transcript cap engaged, but
the oversize documents were ones it doesn't measure:

- finished derived rows near 1 MiB from recording-alias `legacy_ids` (up to 128 per file);
- transcript-heavy rows that predate the cap;
- source recordings already at the limit.

`_oldest_pending` re-seeded the same recording every backoff, so one closure froze each owner's
backlog.

`CONVERSATIONS_V3_SIZE_QUARANTINE` (default on): when a one-seed pass's commit is rejected for size and
Firestore names a document on the seed's side (the seed, its rows, or the sources written for them), the
seed and the pending sources the commit writes for its rows go into the builder lease's
`v3_size_quarantine` (all or nothing, at most 64). Nothing the open window or an unlocked seed reaches
transitively is charged to the seed. Unnamed rejections park.
- Closures still load quarantined rows, so claims are never filtered. Live seeding, the pass chain and the
  sweep skip them on bounded passes. Held ids that stop being pending are pruned on the next size park.
- Each hold lasts 24 hours (`v3_size_quarantine_at`); the id is then seeded again, so a repaired recording
  commits and a still-oversize one is set aside afresh. Clearing both lease fields retries at once.
- New quarantines record a degraded `omi_fallback_total`; a full list records an exhausted one.

This change doesn't shrink any document. Rows bloated by alias `legacy_ids` stay quarantined until a
follow-up slims them. `/v1/sync/audio/{conversation_id}/{audio_file_id}` still resolves old client
handles through an alias's `legacy_ids` (`routers/sync.py`), so that follow-up needs a design for that
reader first.

Rollback: set the switch off on the builder runners; stored ids are then ignored.

Readback, as three numbers that are never added together:
- **owners recovering:** parked `document_too_large` owners whose park cleared and whose
  non-quarantined pending rows older than 1 h are draining;
- **work quarantined:** ids in `v3_size_quarantine`, owners holding any, and owners whose list is full.
  Quarantined work stays unrepaired until the oversize document is fixed;
- **parking without attribution:** owners still parked on `document_too_large` with nothing quarantined,
  because Firestore named no document or named one the open or unlocked windows reach.
