# Dark seal-gated audio scheduling

Implements the approved 2026-11-07 pipeline plan with David's A/B/C rulings.
Contract: [pipeline attention](../../listen_pusher_pipeline.mdx#pipeline-attention).
No activation, deployment, merge, index deployment, historical rewrite or production scan.

## Scheduling and custody

Transcription remains eager. For a batch-covered server-batch capture, the native
finalizer hands off its retained recording instead of generating preview-derived
notes before batch projection. Existing text stays available with the existing
transcription/notes pending presentation. Other capture providers keep their path.

The shared sync enrichment callback admits fast notes only after a completed full
seal: recognized batch owner, finish clock, closed bit, no partial receipt, failed
upload, producer token, deletion or discard. The upload and content revisions are
checked again in the notes persistence transaction. A successful partial seal call
is insufficient. Existing retained-tail validation, privacy, producer grace and
projection/member readiness proofs remain authoritative. Unchanged hold snapshots
still settle once without another paid processing attempt.

Unwatched sealed work waits for episode settlement. The existing durable enrichment
obligation carries `pipeline_dispatch_at`: captured span end plus 1,680 seconds,
leaving a 120-second processing reserve within the 30-minute target. Appends and
joins take the earlier accepted deadline. At that instant only a fully sealed
bounded member snapshot can close; its membership, activity and each seal are
rechecked in the close transaction. Unresolved producers stay blocked. The
composer's settle wait is clamped to the same deadline. Accepted deadlines drain
on rollback; they are not job cancellations or custody closure receipts.

The record fast lane uses bounded Redis hints and wakes over the existing
Firestore jobs. Age comes from original enqueue time, not retry availability.
At least a quarter of slots serve oldest work; passes below four slots alternate.
One owner gets at most one hint admission per pass. A seal advances a known parked
retry, never an active/unclassified lease. The existing poll survives lost hints.
This adds no projection ordering: that remains #24731's responsibility.

## Owner integration contracts

- **#23498:** `/v1/users/client-state` accepts optional `home_visible=false`.
  A watched lease requires foreground plus Home or transcript visibility. Generic
  app-open promotion is distinct. Older clients cannot accidentally claim Home.
  Client foreground preview, notices/exceptions, Wi-Fi policy and text backfill
  remain with that owner; this PR changes no app code or provider routing.
- **#24607:** call blocking `demand_processing.promote_owner(uid,
  trigger='api_read'|'mcp_read')` once at the authenticated private-data boundary,
  off the async event loop. App-open edges use the same bounded promotion. It
  promotes at most 20 indexed enrichment obligations and 20 record hints per
  90-second epoch, never another owner. Seal proof remains necessary to advance
  the durable hold. Keep the existing text and truthful notes/episode pending
  state in responses. Call `pipeline_metrics.open_ready` only after that bounded
  snapshot is actually visible; this is **not** notes-complete latency.
- Close-on-seal stays off until #24828's owner provides the verified 100% receipt.
  No producer-grace/repair changes from #24832/#24853/#24855 are copied here.

The separate skip-silence control is reserved dark for the listen owner; no
timer is shortened by this PR. Activation requires wiring and reviewing the
producer-end hook with #23498, rather than inferring capture completion from
the upload of a chunk. The default conversation silence wait remains 120 seconds.

## Metrics and their sources

| Series/report | Source and limits |
| --- | --- |
| `omi_pipeline_stage_seconds` | Committed seal clock in `database/record_audio.py`; captured span/finish to seal, boundary gap at episode attach, explicit user-finalize wait, processing work at the enrichment callback. Separate from existing provider queue/work and composer stage metrics. No user/content labels. |
| `omi_pipeline_capture_to_notes_seconds{attention,lane}` | First durable notes receipt in the existing conversation persistence transaction; `recorded_end` is the capture anchor, attention frozen at seal. Missing capture clocks counted, never zero. |
| `omi_pipeline_close_to_notes_seconds{attention,lane}` | The persisted server seal trigger to first durable notes; watched 2/5-minute target clock under ruling B. Does not erase capture-to-seal delay. |
| `omi_pipeline_open_to_ready_seconds{trigger,initial_state}` | Owner hook at truthful existing-text/pending visibility, per ruling A. The callback must be wired by #24607/#23498; no samples are fabricated here. Pending generated notes, episode readiness and client visible acknowledgements remain separate. |
| `omi_pipeline_notes_rewrites_per_conversation` | Durable `pipeline_attention.notes_versions` minus initial version, observed at each successful changed-revision commit. Per-commit histogram is **not** a census of unique conversations. For a census, deduplicate protected receipt exports by owner/conversation and use their latest stored count; attempts and discarded stale results are paid-usage-ledger inputs, not committed versions. |
| Captured hours and cost | Offline `scripts/finops/pull_captured_audio.py`, from retained source manifests. Physical owner/root/device/channel/clock epoch and actual-rate half-open frame ranges are unioned before UTC day splitting. Live, batch, retries and copies count once; silence/failed transcription still count. Unknown identity/rate/clock coverage remains unknown. |
| Cost numerator | Reconciled cloud billing plus vendor and notes/composer usage receipts, allocated to captured UTC day. Includes idle/busy GPU fleet once, excludes that fleet from the cloud component, and requires network/logging. Modelled or incomplete numerator means no published dollars/hour. Existing `assemble_unit_cost.py` transcription-based allocations remain separate. |
| Pending/censored stock | Existing summary debt/oldest-age and batch finalization/held-row metrics, alongside completed quantiles. Do not expand on missing clocks, missing series or missing fast indexes. |

No new production collector scan, invoice read, all-in savings claim or manifest
schema migration is authorized. `--captured-audio-report` attaches the separately
reconciled aggregate report to the existing finops assembler when its flag is on.

## Flags, ramp and rollback

Remote `pipeline_attention` owner admission is off when missing or unreadable.
Runtime `PIPELINE_ATTENTION_MODE=off` is the umbrella kill switch. `shadow` records
decisions only; `serve` also requires the remote owner grant. These default false:
`PIPELINE_SEAL_FAST_ENABLED`, `PIPELINE_RECORD_FAST_ENABLED`,
`PIPELINE_CLOSE_ON_SEAL_ENABLED`, `PIPELINE_SKIP_SILENCE_ON_SEAL_ENABLED`, and
`PIPELINE_CAPTURE_COST_ENABLED`. Existing demand and surface-reporting gates are
also required for the reused transport/index. No env/cohort state changes here.

The project coordinator names backend/mobile operators before activation.
Shadow: 24 hours, no additional paid work or due-time changes. Dogfood: named
internal owners, 24 hours and 100 eligible closed captures. Then 1%, 5%, 25%,
50%, 100%, each at least 24 hours and 1,000 eligible captures. Coordinator reviews
each eligible receipt within 48 hours, completing or recording a hold by
2026-11-21. No rollout past shadow until owner wiring and staging/device receipts
exist. The F-join full-ramp receipt is additionally required for close-on-seal.

Every step requires zero custody/privacy/stale-revision violations and zero
unchanged-evidence automatic rewrites; oldest debt must not regress. Watched
close-to-notes target is 120s p50/300s p90; full capture clocks remain visible.
Unwatched first notes target is 1,800s. Open readiness follows ruling A. Retain
the independent two-hour alarm. Pause on rewrite share +1 percentage point or
reconciled cost/hour +5% versus concurrent control, with attribution review.
Broad rollout additionally needs measured pendant life >=24h and phone drain
acceptance on Wi-Fi/cellular. The 120s work reserve is proposed, not proven.

Rollback: set attention mode off, seal/record/close switches false; let durable
jobs and accepted deadlines drain through their original claims. Kill capture
reporting and mark its prior report stale. Already-running calls may finish once.
Reverting this lane's code needs a reviewed PR; never erase audio or receipts,
cancel jobs, revert another owner's PR or roll back user data.

## Carried risk register

| Risk | Likelihood / impact | Mitigation and detection |
| --- | --- | --- |
| False seal / lost late tail | medium / critical | Full AND proof, revision fences at notes and episode close; retained-tail/producer tests, stale/refusal counters, retain raw audio. |
| Record seal mistaken for episode boundary | high / high | Close-on-seal off until F full ramp; bounded member proofs and canonical F reconciliation; watch split/rejoin and visible backfill. |
| Cold open target misreported | high / high | Ruling A pending presentation only; separate generated-ready and visible acknowledgements; no cold-work exclusion. |
| Patient rewrites or deadline miss | medium / high | Immutable deadline/fingerprint and one obligation; track durable versions, pending age and composer calls. Reserve needs staging proof. |
| Fresh traffic starves old owners | high / high | Oldest reserve, original enqueue age, owner cap; loaded-aging tests and oldest-age/control comparison. |
| Stale/multiple sessions or Redis loss | medium / medium | Session leases and conservative unknown-state fallback; expiry/logout/fault tests; pause ramp if indexing is unavailable. |
| Realtime consumers stop silently | high / high | No provider suppression in this PR; #23498 owns English notice and exception proofs before its flag. |
| Sole transcript is suppressed | medium / critical | Handoff only for retained batch-covered server-batch captures; onboarding/BYOK/non-Omi unchanged; coverage parity acceptance. |
| Cellular/preview battery loss | medium / high | No firmware or client preview change here; owner Wi-Fi policy/device tests before expansion; >=24h pendant floor. |
| Denominator omission/duplication | high / high | Replayable physical-frame union, unknown coverage, captured-day reconciliation; overlap/midnight/rate fixtures. |
| Cross-owner contract drift | high / medium | Sequence on #24731, owner hooks and current-head recheck; no pg-short dependency or owner-branch edits. |

## Verification status

Hermetic regression and policy tests exercise real scheduling/persistence paths.
Final test commands and receipts are recorded in the PR. Credentialed emulator
contention, full provider-to-pushed-Home acceptance, rendered/device backfill,
phone/pendant power and production reserve/ramp checks are not claimed by local
unit results. Deployment belongs only to the Infra Rollout Coordinator.
