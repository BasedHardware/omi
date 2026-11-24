# Local-preview leakage stays in server batch before streaming fleet retirement

The [local-preview contract](../../listen_pusher_pipeline.mdx#mobile-local-preview-lane-kill-switch-default-on)
now promotes an admitted session's unexpected pendant audio to durable batch custody.
`LISTEN_PREVIEW_BATCH_CUSTODY_ENABLED` defaults on. Before the first decoded frame is
appended to the durable archive, one Firestore transaction per recording claims
`batch_live_v1`, preserves external metadata and records `server_batch_only` plus
`listen_preview_batch_custody` in `external_data`. Auto/undeclared capture language
is `multi`; a learned English profile never relabels the retained audio.

A missing/deleted/locked/non-recording row, conflicting owner, revoked storage
consent, custom STT, phone call, onboarding, or a non-durable archive leaves the
existing deferred live-open path available. Failed claims are not retried per
frame. Successful claims suppress provider initialization, clear only the STT
forward buffer, and retain originals. Archive commit records exact sample bounds;
normal teardown registers the deterministic batch job even with zero live words.
The first-frame claim/archive handoff is joined through owner cancellation
(including repeated cancellation); decoded-buffer bookkeeping completes before
teardown so a late claim cannot lose its original frame.
The marker is a durable admission receipt on reconnect, independent of the
new-admission cohort/profile gates, but still subject to consent, language match,
custom STT, pusher, onboarding, phone-call and channel safety checks.

Plain `parakeet` is removed from streaming defaults and explicit streaming
selection. `STT_STREAMING_PARAKEET_SLOT_ENABLED=true` restores its default
last-resort hop and connection fallbacks before fleet-off, including sessions
with a pinned two-vendor model list. No runtime model literal change is required;
Modulate and Soniox keep their order unless the client requests Parakeet. The `parakeet-window` listener lane, prerecorded order and PTT order
are unchanged. `STT_GPU_FLEET_OFF` wins over the rollback switch, and Windows
PTT/transcribe continues selecting Modulate.

Parakeet-only hermetic wire and emulator stacks explicitly enable the plain
slot to exercise their local provider stub. With the slot off, a stale plain
streaming list gains the canonical Modulate/Soniox fallbacks in the effective
model getter, including pinned managed sessions; supported English no longer
ends at admission with 1008. PTT model lists and the window-only lane keep their
separate surface policies. Production listener and pusher values already list
the vendors. The gauntlet's optional bounded `--startup-timeout` changes only
local process bind deadlines on loaded hosts; its default budgets are unchanged.

Lead applies after PR review/CI: deploy listener, pusher and backend/backend-sync/
backend-sync-backfill/backend-integration from the same merged revision. Defaults
need no env override. This PR does not activate fleet-off or alter GPU replicas.
The planscost lead first enables promotion on one listen pod or selected cohort.
Verify running release identities and a preview-audio canary that produces an
outbox receipt, a batch job, final words and speaker labels within 30 minutes,
without a duplicate live provider socket. Keep the on-device preview UI. These
sessions already own a batch obligation and use the qualified batch pipeline;
the removed stream is duplicate work, so live p95 is not their acceptance target.
Watch the T2 `terminal_speech` guard and promoted-session counters for one hour
before the lead expands fleet-wide in the same apply session. Roll back promotion
with `LISTEN_PREVIEW_BATCH_CUSTODY_ENABLED=false` if that gate fails.
Watch `omi_listen_preview_batch_custody_total{outcome}`, local-preview deferred
opens, outbox failures/would-drop, batch intake/terminal speech and exhausted STT
fallbacks. Duplicate WAL/listen delivery is a residual risk; inspect merge/dedupe
outcomes. No production canary or measured duplicate rate is claimed here.

Rollback new promotion with `LISTEN_PREVIEW_BATCH_CUSTODY_ENABLED=false` and
redeploy. Existing claims finish in batch. Restore the pre-fleet-off plain hop
with `STT_STREAMING_PARAKEET_SLOT_ENABLED=true` and validate manifests with that
same value if changing model literals; revert is the full restoration. Restoring
retired GPU routing after fleet-off requires ready capacity first, per the
[fleet retirement ladder](../../operational/streaming-gpu-retirement.md).

Evidence: `tests/unit/test_listen_preview_batch_custody.py`,
`test_streaming_parakeet_slot.py`, `test_stt_provider_policy.py`, and
`test_gpu_fleet_retirement.py`.
