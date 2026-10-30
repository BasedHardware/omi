# Temporary voice evidence for sync-off batch users

[ADR-0004](adr/0004-sync-off-speaker-centroids.md) records David's approval.
Voice vectors are biometric-like derived data, although they contain no playable
audio. Sync-off batch processing may temporarily retain only normalized Omi-v2
float32 voice centroids: original unit label, measured exclusive speech seconds,
embedding-space/schema version, capture time and expiry. No text, names, person
IDs or audio enter this artifact. No `audio_files` entry is created and raw-audio
retention is unchanged. This evidence never teaches or enrolls a voice profile.

Projection extracts from already staged audio before enrichment and cleanup.
The `/v2/embedding` extractor is Omi-v2 (`wespeaker-resnet34:v2`), not Community-1
internal vectors; incompatible dimensions/versions fail closed. Exclusive turn
unions prevent repeated/overlapping speech from inflating evidence. Limits:
32 labels, 64 KiB per unit (base64 float32), one 15s clip per label, 8s extraction
budget; 1,024 groups and 2 MiB per conversation pass. Unavailable evidence keeps
anonymous groups. Linking/naming reuse the authoritative batch constraints and
calibrated name matcher; names cannot merge groups and manual receipts win.

Artifacts use the existing staging bucket's hashed owner prefix under
`voice_evidence/`, owner-derived AES-256-GCM for standard **and** enhanced users.
AAD authenticates owner, unit, original generation-pinned audio URI, capture
start/duration, conversation admission identity, protection/privacy generation,
artifact kind, schema, embedding space and hard expiry. A reference alone is
insufficient: reads verify the persisted unit-to-conversation projection, current
privacy generation, registered artifact and effective expiry before and after IO.
No cross-conversation embedding cache, durable aggregate centroid or disk fallback
is populated. Old contributors never gain lifetime when linked to new units.

Hard expiry is 24h from capture. Successful batch completion shortens the
registered deadline to the earlier of that limit and completion +1h (completion
may precede conversation finalization, so this is conservative). Reads refuse at
the deadline even if scheduled deletion has not run. Registration after a racing
completion derives the same earlier deadline. Uploads cannot start inside the
last 30 minutes of that deadline, bounding uncertain-upload lifetime.

The existing deletion outbox registers every immutable create-only object name
**before** upload, then pins the successful generation. The regular batch
maintenance cleanup deletes due objects even when processing failed or remains
pending; only after object deletion does metadata receive its receipt TTL.
Uncertain upload names stay reachable through that outbox. Audio incident holds
do not extend these optional vectors. Account deletion sweeps the owner prefix
and registered artifacts; conversation deletion and protection changes use the
existing purge and privacy-generation fences. Deletion during IO refuses the
result and deletes the exact uploaded generation. No bucket, key or IAM change.

Before creating vectors, the runtime reads bucket metadata and requires explicit
zero-second soft delete, no default event hold, and no retention period. An
unreadable/unknown policy leaves speakers anonymous and creates no artifact.
The lead must qualify that policy and runtime metadata-read access before rollout;
the existing accepted-audio lifecycle audit alone does not check soft delete.
Processing never changes bucket policy or grants access to bypass this check.
GCS documents that soft-deleted objects cannot be permanently deleted during
their retention window ([bucket resource contract](https://docs.cloud.google.com/storage/docs/json_api/v1/buckets)).

`BATCH_SYNC_OFF_CENTROIDS_ENABLED=false` stops creation and consumption while
existing deadlines and erasure continue. The parent
`BATCH_CONVERSATION_SPEAKERS_ENABLED=false` also stops both. Both default on;
admission stays in the existing batch cohort. The lead owns rollout and verifies
speaker counts/names, manual edits, abstentions, latency and physical expiry.
Deploy the Cloud Run processing/projection hosts and Pusher; no GPU model change.
