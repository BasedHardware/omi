# Owner cancel for uploaded, untranscribed recordings

Before this change, deleting an uploaded recording on the phone removed only the phone's copy. The
server job kept its staged audio. A Free owner's `allowance_held` units were released when the
usage period reset and were transcribed weeks after the owner deleted them.

`DELETE /v2/sync-local-files/{job_id}` (owner auth, polling limiter, account destructive-operation
gate) now cancels a batch upload (`bp_` handle) and erases its server copies.

- **Fence (one transaction).** The fence reads the intake, the content ledger and every sibling
  unit. If the ledger is `completed`/`partial`, it answers `already_processed` with the conversation
  ids. If any unit is leased, `result_ready`, committed, running a provider call or a paid/operator
  recovery, or is in any other non-detached state, it answers 409 `sync_job_processing`. Otherwise:
  - Queued units are unlinked from the owner's FIFO.
  - Allowance-hold counts are released.
  - Every unit becomes the existing terminal `privacy_blocked`, with `merge_pending=false`, no
    lease, `next=''`, and `owner_cancelled_at`.
  - The intake is stamped `owner_cancelled_at` and the ledger becomes `owner_cancelled`, without a TTL while cleanup is pending.
- **Erase (retryable).** For each fenced unit, the staged audio/result objects, the artifact rows
  and the job/result rows go first, reusing the privacy purge helpers with a per-transaction
  re-proof of the fence. Then the private-cloud raw originals go: use the intake’s
  exact archive paths, including reused originals from earlier attempts. Old rows can also match
  the upload ID in archive metadata. If an older row has no exact paths and an unlinked original
  has no matching job ID, preserve the object and leave erasure pending. Preserve linked
  conversation originals. Start the 45-day
  receipt TTL only after erasure succeeds. A failure answers `erasure: pending` and the phone
  keeps retrying until the server settles the request.
- **Status.** A cancelled upload polls as `failed` with `reason_code=owner_cancelled`. Sibling
  recordings from the same upload that were not deleted return to phone custody and re-upload by
  themselves.
- **Legacy uploads held in cap holds.** A legacy (non-`bp_`) handle resolves to the owner's one
  content-ledger row naming that job (`stt_cap_hold_v1`, `held`). One transaction reads the ledger,
  every hold it names and the held-audio summary. A hold that recovery has leased, completed,
  handed to batch, or that is still staging/sealing answers 409 `sync_job_processing` and nothing
  is written. Otherwise each `held`/`retained` hold becomes `owner_cancelled` (unclaimable, unlisted,
  not redriven, zero remaining seconds), the summary drops its seconds, and the ledger becomes
  `owner_cancelled`. Erasure then deletes each hold's audio/metadata objects and row
  (`cap_hold_erasure.erase`, after re-proving the fence) and the unlinked raw originals. A ledger the
  recovery already completed answers `already_processed`. Legacy admission in every mode treats
  a cancelled ledger as terminal, and the ledger keeps its cleanup references until erasure succeeds.

Not covered:
- Coalesced uploads and live-record handoffs (`bp_wh_`) answer 409 `sync_job_not_cancellable`.
- Legacy Redis jobs with no held ledger row (dark since 2026-11-04, 24 h TTL) answer `not_found` or
  `not_cancellable`.
- Shadow-evaluation rows, which expire in 7 days.

Kill switch `SYNC_JOB_OWNER_CANCEL_ENABLED` is on unless off. Off answers 503
`sync_job_cancel_disabled`; fenced uploads stay fenced.

Code and evidence: `utils/sync/owner_cancel_endpoint.py`, `utils/batch_pipeline/owner_cancel.py`,
`utils/sync/owner_cancel_legacy.py`, `tests/unit/test_sync_owner_cancel_legacy.py`, `utils/batch_pipeline/owner_cancel_erase.py`,
`tests/unit/test_sync_owner_cancel.py`, `tests/unit/test_sync_owner_cancel_endpoint.py`.
