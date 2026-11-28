# Whole-unit language proof for native records (SCA-4892)

See the [server batch and batch admission language contracts](../../listen_pusher_pipeline.mdx).

For existing native record owners, the full-record drainer and partial-page admission use the
account profile from artifact privacy authorization. When `pin_untrusted` applies, the
conversation language stays in the projection binding and the encrypted unit manifest starts
proof with `multi`. Existing `batch_sync_v1` owners use the sync intake language policy.
Explicitly unsupported declarations continue through the native provider outbox.

Both classifiers must approve each 30-second window for Parakeet. A refused or inconclusive
proof freezes `und` and `unavailable` for the worker language barrier and multilingual
recovery. A privacy or consent denial aborts staging and leaves the durable obligation for
retry. The intake receipt stores the version and bounded language and evidence labels from
the frozen manifest. It carries no profile counts, audio, or transcript text.

Both `BATCH_MULTILINGUAL_PROFILE_ROUTING_ENABLED` and
`BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED` default on. Setting either to `false`
restores the declared native route for this profile cohort. Server-batch auto-language
proof retains its existing gate. The change applies as new units are admitted.

A proof attempt rematerializes each retained unit. With speech and uninterrupted approval,
a 5-minute partial unit can evaluate up to 10 windows and a 1-hour full unit up to 120.
Each window can invoke one vendor and one self classifier, so the respective ceilings are
10 and 120 invocations per classifier per unit per proof attempt. Silence and early refusal
can reduce that work. These are configured bounds, separate from observed production volume.

The 467 focused backend tests on multica-worker-1 included full and partial admission,
proof acceptance and refusal, both rollback switches, and metadata-restore retry. After deployment, use read-only access
for a consenting flagged account to compare native admission evidence with worker and recovery
provider counts. Verify multilingual speech enters a multilingual route or `und` recovery,
and that any Parakeet admission for the affected cohort has `audio_lid` evidence. Report
only aggregate counts. Production evidence is pending deployment. [PR #26488](https://github.com/BasedHardware/omi/pull/26488)
