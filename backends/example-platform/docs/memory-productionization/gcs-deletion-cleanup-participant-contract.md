# GCS `external_objects` cleanup participant

This is a route-free, opt-in deletion participant. It does not change runtime defaults or choose a product deletion policy. A caller supplies a sealed, held write-fence session and an authenticated JSON transport; credentials and object contents never enter the participant, client, or durable receipts.

## Registry and ownership

The branded registry is a flattened list of **8–32 unique `(role, bucket_name)` resources**, sorted by role and bucket. Every semantic role must appear at least once. The eight roles are `speech_profiles`, `conversation_recordings`, `private_sync_chunks`, `private_sync_audio`, `private_sync_merged`, `private_sync_playback`, `temporal_sync`, and `chat_files`. Multiple locations are intentional (for example, the historical `speech-profiles`/`profiles` bucket mismatch); each location has its own policy and coverage digest and its own durable receipt key.

The canonical account id is not assumed to be a legacy Firebase UID. The held fence returns a sorted, non-empty list of opaque legacy owner keys (at most 32 keys and 128 bytes each) and an `owner_mapping_digest`. The participant recomputes and verifies `sha256({version:"gcs-legacy-owner-mapping-v1", account_id, legacy_owner_keys})`, derives the role prefixes internally, and binds that digest into every list/delete request, set digest, and receipt. Raw keys and prefixes do not cross the caller boundary.

## Enumeration and deletion

Each resource is listed with `versions=true` and with `softDeleted=true` as separate modes. The versions listing already includes the live generation; a separate live listing is never added, avoiding double counting. Pages are fixed at 1,000 objects and the participant caps a resource at 100,000 objects and 1 TiB. Empty continuation pages, malformed or cycling tokens, duplicate identities, cross-resource coordinates, and over-limit results fail closed. Objects are represented only by name, generation, metageneration, size, timestamps, hold flags, and mode.

Any soft-deleted, retention-held, or retention-expiring object blocks physical-zero disposal. Otherwise deletion uses the exact object generation and metageneration preconditions. The participant freezes the completed inventory and deletes that exact set; it does not re-enumerate while deleting. A provider 404 is replay-safe `already_absent`. Per-resource receipts include the pre-delete count/set digest, provider receipt digest, owner mapping digest, and receipt digest. A retry re-enumerates and re-deletes any resurrected generation before returning the existing durable receipt.

## Failure and privacy boundaries

The held-fence callback is single-use. Pending provider operations are drained before release; late or captured callbacks fail before provider I/O. Provider and repository failures are mapped to content-free participant errors. This slice intentionally leaves route wiring, default activation, cleanup approval/retention policy, and live-provider qualification to the owning integration and David's production decision.
