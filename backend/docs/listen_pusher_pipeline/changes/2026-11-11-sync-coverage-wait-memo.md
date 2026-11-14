# Memoize repeated WAL coverage waits

A completed negative coverage check for `audio_coverage_unproven` writes a
30-second Redis memo keyed by owner, conversation, WAL content ID and the current
record-job snapshot. A later admission with the same key skips re-running the
coverage wait computation. Another WAL or a changed job snapshot receives its
normal coverage check; hits do not extend the memo's expiry. Proved coverage and
errors are never memoized. Ownership, privacy and receipt checks still run.

The admission decision and custody are unchanged: unproven coverage still returns
503 with the same response body and headers, and the client retains the WAL.
The memo only avoids repeated server work, including artifact lookup, decode and
byte comparison. It does not mean fewer 503s or retries, and no cost reduction is
claimed; realized hit rate and net savings are unmeasured.

`SYNC_RECORD_COVERAGE_WAIT_MEMO` defaults on, with `"true"` in both dev/prod listen
charts and the generated `runtime_env` manifest. Set it to `false` to bypass both
memo reads and writes, including existing entries, and restore the prior coverage
check path. This is the kill-switch rollback; it does not change custody.

Contract: [coverage-wait memo environment setting](../../listen_pusher_pipeline.mdx#server-batch-only-capture-by-platform).

Evidence: [PR #25097](https://github.com/BasedHardware/omi/pull/25097),
[pre-review finding: required pipeline note and environment contract](https://github.com/BasedHardware/omi/pull/25097#discussion_r4534388018),
and the [flag registry row](https://github.com/BasedHardware/omi/blob/b60a6b632667657c43c0199b734926e6bd4c390e/backend/docs/feature-flag-registry.md#L634).
