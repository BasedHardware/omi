# Batch identity evidence continuity

Sync-on authoritative batch resolution defaults to original-unit evidence under
`BATCH_ORIGINAL_IDENTITY_EVIDENCE_ENABLED`. Set it to `false` to restore the
playback-manifest resolver. This switch does not change final-pass admission;
keep integration's existing final-pass exception.

The resolver reconstructs projection membership from generation-pinned unit
results and PCM using the final pass's read-only reference checks. Rebased row
offsets never select audio. Shared units, foreign receipts, expiry, erasure and
privacy generations remain refusals. Merged rows are eligible only when current
receipts already bind every reconstructed unit to that row; this does not
rebind a donor or relax the existing `skipped_merged` refusal.

At most one <=15-second Omi-v2 clip per eligible original label replaces
per-sentence extraction. Original overlapping voice turns are subtracted.
Capture-clock overlap across units contributes no duplicate measured evidence.
Pinned reference and current member geometry bind encrypted conversation-cache
entries. There is no new artifact kind, enrollment or retention extension.
Distance <0.50, owner/person margin >=0.10 and >=5 measured seconds remain the
shared naming policy. There are no added STT, diarization or final-pass calls,
capacity changes or larger embedding-attempt/time budgets.

`input_membership_sha256` identifies the transcript used by the latest resolver.
Late append/merge revokes the completed-owner retry shortcut; the canonical
processing transaction refuses a stale membership. The current processing owner
must resolve and persist the latest transcript. This introduces no retry queue.
The immutable first-resolver diagnosis is retained alongside `current_resolver`.

## Measurements

Read the revision and attempt families below directly from GMP's
`omi-cloud-run-application-metrics` job. The sync profile retains these explicit
families; the shared backend profile already retains `omi_.*`. They have no
in-cluster dashboard or alert consumer, so the Stackdriver exporter bridge does
not import them. Its existing owner-recognition conversation family is unchanged.

The existing completion observer and identity-only CAS observer re-read the
latest committed row. A row-local digest and one of 16 durable aggregate shards
commit together. Duplicate delivery, restart and summary-only enrichment do not
count it again. A later membership or identity change is a **new revision
observation**, not a new recording. This is an observed population, not a census
of all kept rows; a crashed/missing completion callback may omit an observation.
No transcript, user, voice, unit or conversation identifier is exported.

`omi_owner_recognition_identity_{segments,segment_seconds,words,word_seconds,word_time_segments}_total`
uses only `identity=owner|known_person|unknown`. Segment seconds include pauses
inside a stored segment. Word seconds are the union of proven reconstructed word
intervals, available only where original-unit evidence supplied timing. Missing
word time is unavailable, not zero coverage: always publish
`word_time_segments / segments` beside the word-time share. The internal timing
scalar is stripped from public JSON and does not authorize identity or custody.

The existing enrichment maintenance refreshes all durable shards. Scraping does
no Firestore IO. Replicas mirror counters: deduplicate with `max by (identity)`
before computing increases, for example:

```promql
increase((max by (identity) (omi_owner_recognition_identity_segments_total))[6h:2m])
increase((max by (identity) (omi_owner_recognition_identity_word_seconds_total))[6h:2m])
time() - max(omi_owner_recognition_identity_observed_at_seconds)
```

No complete refresh means no exported series. Failed refresh retains its old
freshness timestamp. Validate freshness and export on the traffic-bearing
backend, sync, backfill, integration and relevant worker roles after deployment;
source tests cannot establish that every role exports.

`omi_owner_recognition_proof_refusals_total{reason}` records bounded proof
refusals per resolver attempt. `omi_owner_recognition_final_pass_availability_total`
records disabled, ineligible, admitted and dependency_unavailable invocations.
`omi_owner_recognition_batch_embeddings_total{outcome=attempted|successful|cached}`
counts replacement work directly, without calling it GPU seconds.
These process counters are attempts, separate from durable revision observations
and first-finalization events. True centroid cache hits are counted directly;
abstained or removed candidates never become inferred cache hits.

Expected improvement: more currently supported unit labels reach the existing
constrained linker without a second acoustic pass. Compare fresh-revision segment
and measured word-time availability, proof refusals, extraction attempts per
speech hour, processing time and existing dependency/cost metrics. Lower
fragmentation or higher owner-label share alone does not establish correct-owner
recall or false-owner precision. Those need separately authorized labeled audio
fixtures; this change does not replay private audio.
