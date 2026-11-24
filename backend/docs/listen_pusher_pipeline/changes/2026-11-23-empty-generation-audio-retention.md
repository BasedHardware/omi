# Empty listen generation audio retention

SCA-2533 removes the storage purge from automatic empty-generation teardown.
The existing fenced transaction can discard the empty recording and remove
its conversation row. After the commit, the lifecycle inventories object
versions under the conversation’s `chunks`, `audio`, and `raw-live`
prefixes and emits one INFO record with the retained count. A storage read
failure records an unknown count and leaves the teardown successful. Raw and
derived audio stay in storage.

Explicit privacy erasure and merge cleanup still use their existing deletion
entry points. Their shared purge can continue past disappeared or stale
generations, reports protected objects and provider errors, and verifies the
remaining objects. The `record-wal` sweep uses generation-conditional,
fail-fast deletion. Account deletion applies its strict hold checks.

## Rollout and verification

The retention behavior takes effect when the backend revision in
[PR #26103](https://github.com/BasedHardware/omi/pull/26103) is deployed.
It requires no new flag, environment setting, or migration. Existing lifecycle
admission controls continue to govern when the automatic teardown runs.

Local regression coverage includes the fenced orphan-repair deletion, the
quiet check that leaves an ineligible row alone, and the teardown’s read-only
inventory and storage-read failure paths. See
[`test_record_orphan_repair.py`](../../../tests/unit/test_record_orphan_repair.py),
[`test_conversation_quiet_finalization.py`](../../../tests/unit/test_conversation_quiet_finalization.py),
and [`test_empty_conversation_audio_cleanup.py`](../../../tests/unit/test_empty_conversation_audio_cleanup.py).

After the revision has served for one day, check that Cloud Error Reporting
group `COq2w_fF6o7I3gE` has stopped receiving events. For a newly discarded
empty generation, verify that its raw objects remain and the worker logs one
retention INFO record. Production evidence is pending rollout.

See the [conversation lifecycle](../../listen_pusher_pipeline.mdx#2-conversation-lifecycle-silence-timeout-path)
and [retained-audio custody rule](2026-11-09-token-lease-review-fixes.md).
