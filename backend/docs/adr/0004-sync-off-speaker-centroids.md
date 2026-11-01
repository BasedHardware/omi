# 0004. Speaker evidence for sync-off batch units

- Status: **Accepted** — David approved option 2 on 2026-10-25 ~14:45Z.
- Date: 2026-10-25
- Deciders: product owner (David). Split from the retained-audio fix by lead ruling `846abb` (10:00Z).
- Owner: lead for rollout; qualfix2 for implementation and qualification
- Review by: 2026-10-27 (decision requested by 2026-10-26)

## Context

Batch diarizes conversation-sized units separately. Cross-unit linking and owner
naming (#23581, merged and deployed 13:42Z) reuse retained private-cloud audio, so they work only
for users with private-cloud sync on. For sync-off users, unit audio is ephemeral
and cleaned up after processing, and their unit speakers stay anonymous. Linking
them later needs some speaker evidence to outlive the audio. Voice embeddings are
biometric-like derived data, and audio-storage opt-out must not silently become
permission to keep voice vectors.

## Options

1. **Keep anonymous unit speakers for sync-off users.** No new data. The record
   lane contract states the limitation. Naming for these users stays below legacy.
2. **Temporary owner-encrypted voice centroids** (design:
   `qualfix-sync-off-centroids-design-2026-10-25.md` in the rollout records).
   Omi-v2 normalized float32 centroids per unit label, no audio, text, names or
   person IDs; ≤32 labels and 64 KiB per unit, ≤2 MiB per conversation pass;
   AES-256-GCM with the owner key and AAD over owner, unit, audio generation,
   clocks, embedding space and privacy generation; hard expiry 24h after capture,
   1h after finalization, enforced on read; registered in the deletion outbox
   before upload; kill switch; existing batch cohort first.
3. **Retain sync-off audio longer.** Rejected in the design: it extends raw
   audio retention, which option 2 avoids.

## Decision

Option 2. Approval source: David's 2026-10-25 ~14:45Z instruction, recorded in
the rollout brief `swarm/briefs/qualfix2-syncoff-centroids.md` and anx card
`qualfix-sync-off-centroid-decision`. Implement in a separate PR with CI and a
Luna privacy review; hand off unmerged. No production writes or deploy grant.
The existing parent kill switch and default-on `BATCH_SYNC_OFF_CENTROIDS_ENABLED`
sub-switch bound the existing admitted cohort.

## Consequences

- Option 1: no privacy change; a permanent naming gap for sync-off users.
- Option 2: a new artifact kind in authorization, retention and purge coverage;
  qualification must prove refusal after expiry and physical cleanup; legal-hold
  policy must be resolved first.

Temporary vectors follow the approved hard TTL, including pending or failed
processing. The audio incident-preservation hold applies to recoverable audio,
not this optional derived evidence; it cannot extend vector retention. Existing
batch cleanup has no separate legal-hold extension for this artifact. Account,
conversation deletion and privacy-generation revocation remain authoritative.
There is no new legal-hold override or configurable extension of the vector TTL.
Creation also requires verified bucket metadata with soft delete disabled and no
retention/default event hold; unknown or unreadable metadata abstains. The lead
qualifies the existing bucket and runtime read permission before rollout. This
PR makes no bucket or IAM changes.

## Implemented in

`utils/batch_pipeline/voice_centroids.py`, `voice_evidence.py`,
`database/batch_voice_evidence.py`, and
[retention and deletion contract](../batch-voice-evidence-retention.md).
