# 0004. Speaker evidence for sync-off batch units

- Status: **Proposed** — pending the product owner's privacy/retention decision. No decision is recorded here.
- Date: 2026-10-25
- Deciders: product owner (David). Split from the retained-audio fix by lead ruling `846abb` (10:00Z).
- Owner: the lead, for the decision; the batch speakers lane (qualfix) for the design
- Review by: 2026-10-27 (decision requested by 2026-10-26)

## Context

Batch diarizes conversation-sized units separately. Cross-unit linking and owner
naming (#23581, in review) reuse retained private-cloud audio, so they work only
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

None yet. Until a decision, sync-off behaviour is unchanged (option 1 in effect,
not ratified).

## Consequences

- Option 1: no privacy change; a permanent naming gap for sync-off users.
- Option 2: a new artifact kind in authorization, retention and purge coverage;
  qualification must prove refusal after expiry and physical cleanup; legal-hold
  policy must be resolved first.

## Implemented in

Nothing. The decision is tracked on anx card `qualfix-sync-off-centroid-decision`.
