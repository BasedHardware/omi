# Terminal acknowledgement for user-managed sync anchors

Related contract: [terminal batch assignment supersession](../../listen_pusher_pipeline.mdx#terminal-batch-assignment-supersession). Related change: [PR #26342](https://github.com/BasedHardware/omi/pull/26342).

## What changed and why

When sync assignment raises `SyncAssignmentSuperseded`, the affected request path now treats that outcome as terminal. Cloud Tasks deliveries are acknowledged and their existing completion/claim cleanup runs; late transcript batches are dropped from the socket retry path; bridge and projection follow-ups keep the source conversation canonical and continue processing siblings. This prevents the same user-managed anchor from turning into an unhandled request error and repeating on client retry.

The existing user-authority guards remain unchanged. This mapping does not recreate or redirect the protected row, add a schema field, or introduce a new state store; it reuses the existing terminal completion and cleanup path.

## Rollout and flag state

There is no new feature flag. The mapping is active for this specific exception as soon as the code is deployed. Revert the mapping change in PR #26342 to restore the prior request behavior; the assignment guards remain in place.

## Verification evidence

The PR adds focused coverage for the size-backstop retry, terminal Cloud Tasks acknowledgement, late transcript acknowledgement, bridge/projection completion, and sibling processing:

- [Size-backstop retry](../../../tests/unit/test_sync_size_rollover.py)
- [Cloud Tasks acknowledgement](../../../tests/unit/test_sync_cloud_tasks.py)
- [Late transcript acknowledgement](../../../tests/unit/test_late_audio_recorded_time.py)
- [Projection bridge completion](../../../tests/unit/test_batch_pipeline_projection.py)
- [Pending live bridge](../../../tests/unit/test_sync_pending_live_bridge.py)
- [Sibling processing and terminal reprocessing](../../../tests/unit/test_sync_superseded_terminal.py)

The PR description records that the worker reported targeted and related backend suites plus Black passing on the original patch, and that the published pre-note head passed `git diff --check`. CI must revalidate the updated head. After release, send a request for a conversation with manual speaker assignments and confirm it returns a terminal success; then check Error Reporting group `CML4vsS6tu31bA` for a full day and confirm it stops growing, as specified in SCA-2532.
