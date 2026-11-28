# Bounded wait for v3 playback pieces

Conversation audio merges now treat v3 source readiness failures as bounded
waits. When metadata or chunks for the requested recording windows are late,
the worker schedules up to six replacements after 60, 120, 240, 480, 900 and
900 seconds. Each replacement re-reads the source snapshot and proceeds only
while the requested windows are unchanged. A failed replacement enqueue keeps
the original delivery retryable; if enqueueing still fails on its final
attempt, the worker writes the existing `merge_failed` marker so playback
polling can start the marker-generation recovery path.

If the six readiness deferrals are exhausted, the worker records
`piece_readiness_expired` for the current playback fingerprint. That marker is
terminal for that fingerprint. A changed source-metadata snapshot can create a
new fingerprint and recover; chunk bytes arriving after expiry without a
fingerprint-changing metadata update do not clear the marker. Expiry-marker
writes respect destructive-operation gates and defer while a gate is active.

There is no new feature flag. The behavior applies when the existing
conversation merge worker handles v3 recording pieces. After rollout, read 24
hours of the serving `backend-sync` revision: confirm the old
`v3_piece_not_ready` retry failures and `audio_merge_failed_final` events are
absent, and count readiness deferrals followed by artifact builds, readiness
expiries, and replacement enqueue failures separately. Merged playback and note
delivery effects remain unmeasured. See [SCA-3568 PR #26125](https://github.com/BasedHardware/omi/pull/26125).
