# Owner-lab replay bench

Paired A/B replay of a serving feature (first adapter: the conversation notes
agent) against a frozen snapshot of one consenting owner's account. Arms pin
code refs and env overlays; every run executes in its own subprocess against
its own tree; a file-backed USD ledger stops spend hard, with in-flight
requests charged as reservations; an offline report mode reproduces the paired
statistics without any model call.

## Layout

- `replay_bench.py` — feature-agnostic runner: arms, interleaved repeats,
  resume, spend ledger, transport retry, zero-LLM first-request parity.
- `notes_adapter.py` — the notes agent as a bench feature: production serving
  (`utils/llm/notes_agent_serving` and everything it pulls in) over snapshot
  seams, packet-v2 pinned to the serving default (`shadow` / serve percent 0,
  asserted equal to the unset parser in `qualify`).
- `report.py` — offline report: per-arm table, paired bootstrap 95% CIs vs a
  named baseline, repeat-vs-repeat noise floor, cost split into volume vs
  cache share, acceptance gates (nonzero exit on failure).
- `invariants.py` — label-free invariants and contract-aware identity checks;
  optional labelled cases from an external JSONL.
- `store.py` — read-only in-memory view of a snapshot directory.

## Privacy (hard rules)

The snapshot, bench configs, selections, labelled cases and every run output
hold private data and live **outside Git**, under owner-only file modes (the
bench writes results and ledgers with `0600`). Never commit any of it. No
owner UID, UID digest, email, person name, conversation id, snapshot id or
path, transcript text or case content may appear in code, tests, fixtures,
commit messages or PR bodies — pins and paths arrive through args, env or
files outside the repository (`OWNER_LAB_UID`, `OWNER_LAB_SNAPSHOT`,
`OWNER_LAB_CASES`, the bench config JSON). Grep every diff for 64-hex digests,
emails, UUIDs and snapshot ids before pushing. Never print secrets, UIDs or
emails.

## Setup

1. Snapshot an owner account (the prod exporter lives outside this repo) to a
   directory such as `<scratch>/owner-lab/snapshots/<name>`; pass it with
   `OWNER_LAB_SNAPSHOT`.
2. Check out one worktree per pinned arm and note the commit each sits at.
3. Write a bench config JSON outside Git, next to where results should land:

   ```json
   {
     "repeats": 2,
     "soft_stop_usd": 2.80,
     "hard_stop_usd": 3.00,
     "arms": [
       {"name": "baseline", "adapter": "testing.owner_lab.notes_adapter:build_adapter",
        "tree": "/Volumes/Ephemeral/scratch/worktrees/omi/<baseline>", "ref": "<full sha>"},
       {"name": "on", "adapter": "testing.owner_lab.notes_adapter:build_adapter",
        "tree": "/Volumes/Ephemeral/scratch/worktrees/omi/<candidate>", "ref": "<full sha>",
        "env": {"CONVERSATION_NOTES_AGENT_LOOKUP_EFFICIENCY_ENABLED": "true"}},
       {"name": "off", "adapter": "testing.owner_lab.notes_adapter:build_adapter",
        "tree": "/Volumes/Ephemeral/scratch/worktrees/omi/<candidate>", "ref": "<full sha>",
        "env": {"CONVERSATION_NOTES_AGENT_LOOKUP_EFFICIENCY_ENABLED": "false"}}
     ]
   }
   ```

   The arm tree provides the product code under test (`utils/`, `models/`,
   `database/`). Each worker vendors only `testing/owner_lab` into a private
   directory ahead of the arm tree on `sys.path`, so product imports resolve
   from exactly one place — the arm's pinned checkout — and the harness can
   never shadow it. If the notes lane echoes the requested route instead of a
   billed model, add
   `"billed_model_markers": ["gpt-6-luna", "omi:auto:conv-structure"]`.

4. Gateway: reach the dev LLM gateway through your approved tunnel (a local
   `127.0.0.1` forward), export `OWNER_LAB_GATEWAY_URL` and point
   `OWNER_LAB_GATEWAY_TOKEN_FILE` at the service token file, mode `0600` — the
   token itself never enters the environment or any log. The transport
   reserves each request's worst case in the ledger before sending, refuses
   redirects and proxies, validates the billed model and usage, and the worker
   denies every outbound socket connect except the gateway peer.

## Running

All commands run from `backend/` with the bench module's tree checked out;
`OWNER_LAB_UID` and `OWNER_LAB_SNAPSHOT` must be set (they are never
defaulted).

```bash
.venv/bin/python -m testing.owner_lab.replay_bench --config /path/bench.json --mode select    # zero-LLM selection
.venv/bin/python -m testing.owner_lab.replay_bench --config /path/bench.json --mode qualify   # zero-LLM qualification
.venv/bin/python -m testing.owner_lab.replay_bench --config /path/bench.json --mode parity    # zero-LLM parity
OWNER_LAB_GATEWAY_URL=... OWNER_LAB_GATEWAY_TOKEN_FILE=... \
  .venv/bin/python -m testing.owner_lab.replay_bench --config /path/bench.json               # the paid bench
.venv/bin/python -m testing.owner_lab.report /path/runs.jsonl --baseline baseline \
  --max-cost-per-run 0.006 --no-worse rejections,cost --out /path/report.md                   # offline report
```

`report.py --prices input,cached,output` (USD per million tokens) reprices
every stored run from its token counts when the bench ran on a non-default
card, so the per-arm table, paired ratios, gates and the cost split all use
the same card.

- **select** picks bench cases by tier (7 short / 7 medium / 6 long, filled to
  20) among conversations the eligibility gate would run, and lists labelled
  cases separately.
- **qualify** proves, with zero model requests, that the transport is reached,
  identity and packet wiring match the pinned serving default (including a
  serve-mode probe asserting packet v2), the toolbox redacts screen rows
  outside the conversation window, and the identity contract behaves.
- **parity** fingerprints the first model request per case in every arm and
  compares hashes; arms that share a prompt route must match byte for byte.
- **run** interleaves arms per case and repeat (`arm` order rotates), resumes
  from the results JSONL by skipping already-recorded (arm, case, repeat)
  keys, retries transport stops (exit 3) up to three consecutive failures, and
  stops terminally on the spend stop (exit 4) or any worker error (exit 2).
- **report** reads the results JSONL in place — outside the repo — and exits
  nonzero when a gate fails. `--no-worse` fails only when a metric's 95% CI
  sits entirely above 1, i.e. the arm is significantly worse than baseline.

## Checks on every run

Each run's row carries `invariant_failures` from `invariants.py`: label-free
invariants (sections with nested bullets for long transcripts, no action-item
section, cost under the cap) and the inverted identity check — on the final,
post-repair submission, every human participant and any title name must carry
identity support (voice binding or affirmative user correction). The row also
reports the production repair counters (`repairs_by_kind`:
`accepted_with_problems`, `participant_dropped`,
`unsupported_speaker_identity`). Optional labelled cases
(`OWNER_LAB_CASES=/path/cases.jsonl`, outside Git) carry a
`contract_version`; a case from another contract version reports STALE, never
FAIL, and an expected name is only scored when the snapshot supports it —
without support the identity contract forbids naming that person, so the
expectation is skipped instead of failed.

## Batch speaker final-pass repro

The earlier speaker lab used full private-cloud-sync audio. Production uses the
staged batch units, their projection receipts and retained encrypted results,
then reconstructs segment IDs and assembles audio on each unit's capture clock.
Full playback bypasses scope selection, expired references, merged receipts,
point-word grouping, part geometry and duration checks; its success does not
qualify the production path.

`final_pass_repro.py` calls the real `run_batch_final_pass`, `_units`, `_assemble`
and `_run`. Use the owner-only `guard.py` supplied outside Git (not distributed
with this bench). UID, encryption secret, selected conversation IDs (a JSON
list), and optional diarizer URL must arrive through owner-only `0600` files.
Run from `backend/` with read-only credentials and the production-equivalent
stage/bucket configuration supplied by the operator:

```bash
.venv/bin/python -m testing.owner_lab.final_pass_repro \
  --uid-file /private/uid --secret-file /private/encryption-secret \
  --conversations-file /private/conversation-selection.json --diarizer stub

.venv/bin/python -m testing.owner_lab.final_pass_repro \
  --uid-file /private/uid --secret-file /private/encryption-secret \
  --conversations-file /private/conversation-selection.json --diarizer http \
  --diarizer-url-file /private/diarizer-url
```

The stub returns projection voices on the reconstructed unit word clock and
checks plumbing only. HTTP uses the real `HttpDiarizer`, including production
VAD compaction. Neither result measures slot pressure or spend admission:
`_reserve_budget` admits in-process; recurring learning and label application
are captured without publishing. Application still executes on a private copy,
so grouping and changed-segment counts are checked. The SDK write fence rejects
Firestore document/batch/transaction writes, GCS mutations and Redis writes;
empty read-only Firestore commits remain allowed.

Each JSONL case is identified by selection index (no UID or transcript), with
one terminal outcome, safe code-owned exception message, failing unit, scope
kinds, coverage, changed segments and speakers. The final JSONL row reports
success rate. Keep the selection and output outside Git with mode `0600`.
The CLI suppresses library logs to prevent provider errors from leaking private
content. A missing/undecodable conversation produces `failed_load`, never an
empty-transcript success. Production flags keep their normal values; disabled
or out-of-cohort cases report `skipped_ineligible`.

Rows also report `read_wall_seconds`, `read_bytes`, `read_reserved_bytes` and
`read_objects`, including when reference loading or artifact decoding fails.
Wall time covers reference snapshots, artifact retrieval and reconstruction,
and post-diarization reference revalidation; it includes decode/projection CPU
and excludes assembly, diarization and application. `read_bytes` counts complete
GCS response bodies, including encrypted manifests and retained source objects;
partial transfers that raise inside the SDK are not observable. Reserved bytes
can therefore exceed received bytes. These are GCS payload counts, excluding
Firestore response sizes and protocol overhead. The CLI separately reports
`conversation_load_wall_seconds` for loading the conversation/manual receipt.
Use these fields to distinguish slow local reads from model latency without
changing production's 180-second initial read deadline.
Budgeted artifact reads also use bounded read-only snapshots for their privacy
checks before/after download and after retained-manifest materialization. These
used ordinary Firestore transactions before this fix and could outlive the
remaining budget despite bounded blob reads. Unbudgeted writer authorization
retains its existing transaction path.

Mixed lanes are supported only for positive-duration segments with batch-unit
evidence. Other lanes and point-only segments are preserved. Missing required
batch segments keep their labels while provable covered segments can update,
reporting `partial_coverage` without recurring learning; no reconstructable words
means no updates. Expired artifacts and receipts for another
conversation report `skipped_expired` and `skipped_merged`. Retention starts
at completed projection, after enrichment is queued; reading never extends it.

An artifact row with `expires_at` and no `uri` is a cleanup tombstone:
`cleanup_completed_artifacts` first deletes the object, then removes `uri` and
`cleanup_after` and retains the metadata for 45 days. A future `expires_at`
describes the receipt's TTL, not usable audio. After ownership, generation and
erasure checks, these rows report `skipped_expired` with `artifact_cleaned`.
Live rows still require the exact registered base/pinned URI and a live
`cleanup_after` if present; GCS reads still require the pinned generation.
Results get 24 hours from projection completion. Native-record audio manifests
get 45 days; newly registered artifacts may not yet have a cleanup deadline.

Shared staged units (including projection parts and size-rollover receipts for
another conversation) report `skipped_shared_unit` before any artifact read.
The pass cannot yet trim their audio with sufficient ownership precision.
Recurring centroids must have at least one word assigned to an updated segment
in this conversation; the recurring-profile evidence thresholds still apply.

Slot admission never waits in the shared postprocess pool. Serving direct attempts
claim the same durable content-free obligation as retries before automatic resolution.
A successful direct replay closes it only after canonical persistence, so an old
queued wake cannot infer or count again. Manual overrides remain refreshable on
closed/live obligations. Busy attempts release custody and schedule speaker-only
work in
`batch_pipeline_<stage>_speaker_final_pass_outbox`. Named Cloud Tasks (`bfp-...`)
use the existing enrichment/sync task bindings, with the distinct
`batch_final_pass` kind. This does not mark `sync_reprocess_outbox` or rerun
notes, memories, integrations, or full enrichment.

The initial direct attempt leaves four subsequent claims available per immutable
unit/segment membership. Direct replays of pending work also spend that cap, with
exponential backoff (30/60/120/240 seconds, multiplied by random 0.5–1.5 jitter).
Duplicate wakes are fenced by token and lease. Attempts survive expired leases,
and closed receipts cannot reopen or reset the cap. Sustained contention closes
once with `skipped_slot_exhausted`; other exhausted retries use
`skipped_retry_exhausted`. The existing enrichment maintenance schedule repairs
lost wakes in the dedicated collection. Existing queued tasks keep their token;
repair checks advance separately so queued work cannot pin discovery.

Transient claim/settlement storage failures acknowledge the task with
`deferred_custody`, without an immediate wake or a terminal count. The existing
durable-row sweeper rearms pending rows or expired leases after recovery; the
enrichment queue's unlimited transport retries do not drive this recovery.
An ambiguous committed claim retains its attempt. Terminal settlement leaves a
content-free reporting receipt. Reporting atomically increments a durable counter
and closes that receipt, so an ambiguous commit cannot lose or repeat a count.
The maintenance sweep refreshes the cached durable totals even with no due rows;
Prometheus scrapes perform no database reads. Replica mirrors use `max`, not
`sum`; see the [operator queries](../../docs/runbooks/batch-conversation-speakers.md#reading-final-pass-outcomes).

For four ordinary on-time claims, backoffs total at most 675 seconds (11m15s). That is not a
wall-clock delivery guarantee: queue backlog, outages, a crashed one-hour direct
lease or 15-minute retry leases (including repair wakes) can deliver work after cleanup. A late retry remains
`skipped_expired`, closes the obligation once, and never extends retention.

The retry reloads the current conversation and manual receipt, runs only
`run_batch_final_pass`, and uses the existing revision-fenced identity-only
persistence transaction. Retried inference abstains from recurring-profile
learning: that learner stamps the conversation and would invalidate the identity
CAS. Normal admitted passes retain recurring learning. A changed revision defers
within the same cap. The
consumer records a durable terminal count only after settlement; duplicate
deliveries cannot count it again. Ineligible calls and durable deferrals remain outside
the terminal counter contract. The replay suppresses Prometheus writes inside
`reproduce()`, including counters, histograms and lazy label children.

Retryable Firestore/GCS failures now produce `deferred_transient` from initial
passes and retries: unavailable, deadline, aborted, internal-server and quota
errors, connection resets and read timeouts. The shared batch diarizer adapter
propagates typed transients to the same boundary; legacy lanes retain their
existing fallback. Explicit wrapped causes remain classifiable without parsing
provider messages. Elapsed read deadlines defer; object/byte and unit/audio caps
stay terminal. Permanent reload errors close as `failed_dependency`. The same
four-claim outbox closes persistent transients once as `skipped_retry_exhausted`.
HTTP 408, 429 and 5xx responses follow that transient path after the diarizer's
single immediate retry. Other 4xx and nested TLS verification errors remain
terminal; TLS errors receive no immediate retry.
No SDK retry loop or semaphore wait is added. The read-only lab captures retry
requests as `requeue_calls` without publishing an outbox row or task.

The whole-pass shared-unit skip remains the precision-first default. No partial
processing or recurring learning occurs when any reference is shared or
unsettled. The shared durable terminal counter records `skipped_shared_unit` once per managed
conversation/unit-membership obligation; raw unmanaged calls use
`omi_transcription_final_pass_total{lane="batch",outcome="skipped_shared_unit"}`.
`omi_transcription_final_pass_unit_skips_total` counts each omitted unit with
code-owned reasons: `shared_unit` for rejected references, and
`blocked_by_shared_unit` for the other units omitted with that conversation.
The backend-integration GMP keep-list retains both counters.

The speaker retry/outbox dependency stays out of the **GPU batch-pipeline
worker** import closure. Pusher's finalizer reaches it through
`process_conversation` → `processing_speakers`. Pusher's source closure and its
checked-in `backend/pusher/pylock.toml` were verified: Firestore 2.20.0, Cloud
Tasks 2.16.4, and Prometheus 0.21.1 cover the dedicated outbox. Both the role and
legacy Pusher source surfaces passed closure validation; the role image installs
that Pusher lock.

Round 4 diagnostics include `exception_type` and `location`: the innermost
backend-relative `file:line:function`, without stack locals or arbitrary
exception messages. `unclassified` always retains that location (or the explicit
`unavailable` sentinel when an exception has no traceback). Production
`event=batch_final_pass` failure logs carry the same fields.

Metric isolation supplies no-op children for timers, exception counters,
in-progress gauges, callbacks, decorators and private value reads. Earlier
children lacked these APIs; notably lazy `stt_cap_dispatch` gauge initialization
calls `labels().set_function()`. The multi-unit replay tests exercise the real
unit/reference/assembly/final-pass path, with blob transport and diarization
substituted, rather than mocking the final-pass diarization helper.

Reference failures now distinguish `no_job`, `no_result`, `receipt_missing`,
artifact row/owner/unit/kind mismatch, generation mismatch, erasure and URI
mismatch. Projection validation has `projection_*` codes. Missing jobs are
unproved scopes: they count as omitted segments, never as registered units or
audio to fetch. If no registered unit remains, the result is a specific
coverage failure. Expired, merged and shared-unit dispositions are retained.

There is no 128-unit conversation limit. Admission permits at most 480 distinct
candidate batch-unit scopes, checked before any reference or artifact read.
This is two hours at an average 15 seconds per unit, allowing 20 times the
fragmentation of the producer's 300-second target. It is a resource admission
bound, not a minimum duration assertion: smaller fragments remain valid inside
it. Non-batch lanes do not consume the cap; unknown/no-job candidate IDs do,
because proving their absence itself costs a lookup. Excess candidates report
`failed_too_long` with reason `unit limit` before IO. Registered audio still
charges `max(1, duration_seconds)` against two hours; the artifact-object ceiling
is 1,440 (three per admitted unit). Independent 320 MiB, 180-second read and
two-hour assembled-timeline limits remain.

Reference snapshots are read-only and single-attempt. Begin, document reads
(including privacy/memo reads), and cleanup use the remaining monotonic budget;
each read RPC has a 10-second ceiling with SDK retries disabled. Cleanup uses
at most one remaining second; an expired read-only snapshot expires server-side
without holding a worker. Reference budget failures stop lookup immediately.
Post-diarization revalidation uses the remaining overall 600-second deadline.

Reconstruction sorts only metadata, preallocates one PCM timeline (including
existing decode-rounding tolerance), and consumes one unit at a time. It drops
consumed unit PCM and adjusts word clocks/labels on the same dictionaries.
The diarizer receives a read-only memoryview trimmed to the decoded timeline;
HTTP uploads use 64 KiB byte chunks and restart that iterator on retry.
The maximum-size synthetic stress test covers 480 units, two hours of canonical
16 kHz PCM16 and 21,600 words, with a 288 MiB tracemalloc ceiling for the real
reconstruction/assembly/final-pass path. That bound excludes process baseline,
real VAD/model working memory and external transports; it is not a pod-RSS cap.

`bounded_projection_words` preserves all validated words; EOF tolerance can turn
a word into a point, which provides no voice evidence. Point-only stored
segments remain outside positive-duration coverage. Stored projection IDs can
also differ from current grouping, or name different text at the same index.
Only matching IDs and text with positive word evidence may change labels.
Unplaced positive-duration segments retain their labels, with per-reason
counts in `coverage_reasons`; other verified segments can produce terminal
`partial_coverage`. Partial passes do not learn recurring voices and leave
conversation speaker resolution unavailable. Shared units still skip the
whole pass before reading audio. Complete success rate excludes partial passes.

`projection_segment_missing` means a stored positive-duration segment ID was
not emitted by the current unit/part reconstruction. IDs encode the unit/part
and grouped segment index; changed grouping, older projection versions or
subsequent transcript edits can invalidate that correspondence. The adapter
does not guess an identity from text or rebased conversation offsets.

`conflicting capture clocks` means two authenticated unit capture intervals
overlap but their PCM differs in that overlap. Identical overlaps are accepted.
Retained manifests can have padded holes, including between partial captures;
materialized PCM does not carry an authenticated occupied-slice mask into this
adapter. Neither zero samples nor current transcript offsets prove which unit
owns a conflicting span. The current pass refuses the whole ambiguous timeline.
Recovering such overlaps would require carrying verified manifest geometry;
silencing this check could duplicate speech or choose the wrong voice evidence.

Dated local validation: [2026-11-04 speaker final pass](validation/2026-11-04-speaker-final-pass.md).

Resource validation: [2026-11-05 bounds and peak memory](validation/2026-11-05-speaker-final-pass-resources.md).

Artifact lifecycle findings: [2026-11-05 lifecycle and read diagnostics](validation/2026-11-05-speaker-final-pass-artifact-lifecycle.md).

Transient retry validation and rebase: [2026-11-05 dependency custody](validation/2026-11-05-speaker-final-pass-transient-custody.md).
