# Language-guarded batch recovery

Owner: batch record lane; release and redrive owner: rollout lead/operator.

`worker_failure.reason=unsupported_language` covers both unsupported/blocked and
unknown/blocked routes. Parakeet did **not** run on these units. Recovery first
uses Modulate. If it fails, one independent Soniox async attempt runs before the
unit settles. This does not change general prerecorded or PTT routing and does
not reactivate Deepgram.

The independent attempt has a durable, token/privacy-fenced claim. No HTTP POST
is retried, including uncertain replies. A repeated delivery reconciles only the
create-only encrypted result; it cannot buy another call. An automatic Soniox
attempt also prevents an operator from buying Soniox again for the same unit.

## Dispositions and receipts

- Words from either recognizer recover the unit through ordinary ordered merge
  and projection.
- Two **validated empty** recognizers and less than **512 original samples
  (32 ms)** of strict VAD classify as silence. The result retains original VAD
  spans/seconds and both provider/zero-word receipts in separate measured fields.
  Compare sample counts, so floating-point subtraction cannot clear a full frame.
- Guarded zero-VAD units also run both recognizers before silence. Recognized
  words with zero strict VAD remain held with positive word-count receipts;
  transcript timestamps never fabricate the missing VAD accounting evidence.
  A disabled/capped independent path keeps a zero-VAD obligation prepared and
  buys neither call.
- A full positive VAD frame, unknown/invalid VAD, provider failure or malformed
  response cannot authorize this silence disposition. Keep custody held.
- The job's `recovery.recognizers` / `speech_redrive.recognizers` stores provider,
  outcome, word count (null means unobserved), and measured VAD seconds. The job's
  `measured_held_vad_speech_seconds` remains the T2 census value. `refused` means
  the independent recognizer did not run; it is never counted as an empty answer.
  This census is monotone: `max(prior, new)` across worker, CPU inspection,
  recognizer receipts and failed settlement. A later zero cannot erase prior
  measured speech. Provider receipts retain their own local measurements.
  Prior positive evidence at or above one frame blocks silence even when CPU
  VAD later reports zero; settlement also fences saved-silence replay against
  unknown or positive census evidence.

The same census rule also covers ordinary recovery, paid redrive, silent-only
operator disposition, terminal disposition and shadow settlement/reaping.
Ordinary VAD-only silence requires an explicitly validated zero and no prior
positive speech; guarded subframe silence additionally requires both independent
empty recognizers. Saved results supply their validated VAD measurement to the
atomic settlement fence, so a real zero can reconcile without converting an
unknown or larger prior value into zero. Contradictory saved results stay held.
Legacy no-provider/terminal tools refuse language-guarded units; use the explicit
independent epoch-3 plan. Completed historical receipts remain unchanged.

Ordinary automatic recovery can resolve strict-VAD silence locally before STT.
For that branch, the start transaction records
`recovery.no_vendor_call={version: 1, reason: strict_vad_silence, vad_speech_seconds: 0}`
under the running recovery token and privacy/ownership fences. It proves this
recovery intent selected the local zero-VAD branch and bypassed vendor dispatch;
it is not a vendor receipt or a claim about earlier intake/worker calls. The
existing `recovery.provider` still names the selected route, including Modulate,
and alone never proves a call. The record survives a lost result-storage reply
and reconciliation; a running record alone does not prove completed settlement.
Guarded zero-VAD silence instead retains its actual Modulate and Soniox empty
receipts and receives no `no_vendor_call` record. Existing historical jobs are
not backfilled. Observer proof rules and rollout thresholds are unchanged;
accepting this new record as route proof requires a separate ruling.

Threshold evidence: local Silero evaluates 512 samples at 16 kHz, one 32 ms frame
(`utils/stt/local_vad.py`). Only the clipped final frame can be shorter. Synthetic
tests cover 0/16/32/64/320/4384 ms, the 511/512-sample boundary, and floating-point
subtraction at that boundary. This is a conservative resolution-based proposal,
**not labeled evidence of false positives or the language of any held audio**.
The current measured 64 ms, 320 ms and 4.384 s units all remain held if Soniox is
empty. Their transcripts require recovered words; this fix does not promise the
batch re-ramp will clear.

## Spend and rollback

`BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED` defaults **on** in code.
Explicit deployment overrides still apply; dev and the GPU worker stay pinned off.
Unsupported-language provider jobs whose final attempt is validated empty enter
`held` for the existing Modulate-then-one-Soniox recovery. The route's
`provider_reason=unsupported_language` and the worker failure reason both identify
guarded jobs. Other worker failures remain terminal `failed_held`.
Explicit `false` restores immediate worker `failed_held` and stops new Soniox
attempts. It never falls back to another Modulate call. Rollback:
set it false on the recovery role/operator, retaining all held obligations.

`BATCH_PIPELINE_INDEPENDENT_RECOVERY_MAX_SECONDS` defaults to **60** and can only
lower the hard 60-second per-unit ceiling. Invalid/nonfinite values refuse spend.
Each unit gets at most one independent submission across automatic and explicit
recovery. Company-funded Soniox rechecks the batch allowance even for units
originally admitted with customer-funded credentials. Guarded Modulate dispatch
also rechecks company funding. With the feature enabled, a positive input-bound
worker VAD receipt permits that existing Modulate attempt when CPU VAD has no
spans, including captures above 60 seconds. That existing worker-proof path
is unchanged.

`BATCH_PIPELINE_GUARDED_LONG_RECOVERY_MAX_SECONDS` remains **0** in prod, dev
and code defaults: the long-recovery extension is in its kill state. The code
path is retained, but newly admitted units have neither strict CPU VAD spans
nor a valid input-bound worker speech receipt. Their Modulate words therefore
raise `WordsWithoutVad` and remain `failed_held`; enabling this extension now
would add paid calls without a recoverable new population. The planscost lead
keeps it off following Luna's P1 review.

Before this cap is ever raised, recovery must be able to **accept words with
independent acoustic evidence for that newly admitted population**: obtain and
validate input-bound speech evidence independent of transcript word clocks,
then use it in ordinary accepted settlement with measured speech accounting.
Regression tests must prove the new success path, privacy/funding/one-attempt
fences and unchanged false-silence protections, followed by lead review of the
activation and spend plan. Existing worker-receipt successes are not evidence
that this new population can recover; they already pass the existing gate.

The dormant extension still refuses invalid/nonfinite caps, clamps any future
cap at 7200 s, requires the master recovery flag and rechecks company funding.
It never widens Soniox's 60-second ceiling or relaxes acoustic validation:
Modulate empty retains Modulate `empty` and Soniox `refused` receipts above
60 seconds; words without VAD retain their positive word-count receipt and
stay held. Neither case fabricates silence or reopens an already `failed_held`
intent. Keeping the cap at `0` and redeploying backend-integration preserves
this kill state; existing held backlog remains operator-owned.

The global backfill daily-hours deployment setting is **1665** (3x the prior
555), but binds only if `SYNC_BACKFILL_ADMISSION_LIMITS=true`; that separate
control remains off. Cloud Tasks `sync-backfill-fresh` concurrency remains the
production pacer. Its reviewed in-tree source is
`backend/deploy/ops/prod.yaml` (`cloud_tasks.sync-backfill-fresh`: 90 concurrent
dispatches / 15 dispatches per second). The lead separately sizes that config
and uses `backend/scripts/ops_train.py` / `.github/workflows/config_train.yml`
to plan, apply and verify it; these declarations are not live-state evidence.
The warning rule `omi-sync-backfill-queue-wait-high` watches
p95 `omi_sync_queue_wait_seconds{lane="backfill"}` above 1800 seconds for 30
minutes. The existing buckets jump from 900 to 3600 s (no 1800 s boundary),
so the quantile threshold is interpolated. This histogram samples tasks at execution, so it cannot detect a
fully stalled queue with no dispatches; keep backlog/oldest-ready monitoring.
The lead checks live rule state/history and sizes dispatch capacity separately.
Rollback reverts the hours values and pauses the warning rule.

When worker silence disposition is rolled back, sampled record units that reach
empty ASR additionally emit `strict_silent_asr_empty` from the strict-VAD shadow
counter if strict VAD confirms silence. This observation never changes the
EMPTY_ASR quarantine, payload or accounting. With worker silence disposition on,
this extra inspection does not run. `BATCH_PIPELINE_STRICT_VAD_SHADOW_PERCENT=0`
disables the observation; deploying worker source makes it available for future
rollback qualification.
Polling has a 120 s budget and 60-GET
ceiling; individual requests have at most a 20 s I/O timeout. Cleanup uses two
bounded requests. Recovery never automatically resubmits a timed-out job.

Serving recovery suspends its fenced continuation during Soniox HTTP requests
and polling sleeps. It uses the shared async STT client and semaphore, releasing
the permit between requests; no shared sync-executor slot or database transaction
remains borrowed during this provider wait. The private operator CLI uses its
own synchronous driver. Existing primary Modulate execution is unchanged.

Soniox's published async estimate is **$0.10/audio hour**: approximately
**$0.000556 per 20 s unit**, **$0.001667 at the 60 s cap**. The ten RCA units total
176.527125 s, about **$0.004904 incremental Soniox spend** if all run once; the
ten-unit duration ceiling is about **$0.016667**. These are estimates, not vendor
usage measurements or a guaranteed token bill; actual billing is token-based.
Prior Modulate spend is already incurred and is not included. Valid empty Soniox
responses are metered as accepted provider audio too. Fresh guarded zero-VAD
units now pay for Modulate as well, rather than taking the old VAD-only shortcut.
At Modulate's published **$0.03/audio hour** and Soniox's approximate $0.10/hour,
the two-call estimate is **$0.000722/20 s** or **$0.002167/60 s**. Account-specific
settled usage remains the billing authority; these figures are public-rate
estimates and do not change the existing internal rate card.

Sources checked 2026-10-26: [Soniox pricing](https://soniox.com/pricing),
[model](https://soniox.com/docs/stt/models),
[async request](https://soniox.com/docs/api-reference/stt/transcriptions/create_transcription),
[token response](https://soniox.com/docs/api-reference/stt/transcriptions/get_transcription_transcript).
Modulate: [multilingual batch pricing](https://www.modulate.ai/api-pricing).

The adapter uploads only canonical WAV bytes in memory, with no account IDs,
provenance, public URLs or transcript logging. It deletes only its own temporary
vendor upload/transcription after the attempt. Original Omi artifacts stay in
custody. Cleanup errors emit `event=soniox_batch_cleanup outcome=failed`; a crash
or lost upload acknowledgement can leave vendor data until automatic expiry.
Soniox documents [30-day async retention](https://soniox.com/docs/security-and-privacy).
No live provider acceptance or cleanup has been tested using customer content.

## Existing held units: operator-owned release step

Deploy the CPU backend role that runs `QuarantineRecovery` and use the same source
for the operator CLI. The GPU worker itself does not contain this adapter. Verify
`SONIOX_API_KEY` availability without printing it. David approved binding the
existing secret to production backend-integration (lead ruling ce5485), and this
PR adds only that production binding. Dev remains unbound. No IAM or deploy
workflow change is included. Op1 owns live pre-bind and service-account accessor
verification; if an IAM grant is needed, stop for separate approval. Code and
CPU/worker manifests remain off under ruling 404ca5. The lead owns the
2026-10-26 morning activation/ramp review. Op1 canaries one exact unit and expands
only with clean T1/T2/T4 plus lead approval. A missing key refuses the operator before starting
its paid intent and leaves automatic recovery held with a `refused` receipt.
It does not consume the independent attempt, so explicit recovery can proceed
after the runtime configuration is corrected.

The separately deployed worker imports the same control, so its chart explicitly
pins `worker.independentLanguageRecoveryEnabled=false` as well. Keep this reader
aligned with the CPU flag in the approved activation/config change; the worker
does not receive a new Soniox credential. This PR needs the worker chart wiring
rolled as well as the CPU source, while actual recognition runs on the CPU role.

For the seven untouched epoch-2 units and three spent Modulate epoch-2 units,
use `scripts/batch_pipeline_speech_redrive.py` with **both**
`--independent-language --paid-epoch 3`. It requires exact private
`--unit-ids-file` IDs, the usual owner/time bounds, immutable cohort manifest,
fresh dry-run census/plan digest approval, and explicit serving flags for unpinned
policy. An independent dry run uses metadata only; every selected unit is shown
as a potential paid attempt, not as verified speech. Apply measures VAD in memory.
Run separately per owner, canary with `--apply-limit 1`, inspect only aggregate
receipts, then expand the exact approved prefix. A failed-held canary stops the
script; do not reset its token to continue spending. The operator must obtain
the lead's next instruction for the remaining prefix.

Epoch 1 stays unchanged. For the three already-paid units, epoch 2 is preserved
verbatim as `speech_redrive.prior_speech_redrive`; the new Soniox token is epoch 3.
The approval digest binds that prior token. A running or unsettled epoch 2 cannot
be replaced. Preserve the previous `--silent` setting; replacement refuses a
suppression change. Existing Modulate plans cannot silently switch to Soniox.
Either preserved epoch may supply the valid-empty Modulate evidence; a recorded
error is never converted into an empty result merely because another stage's
failure code says `empty_asr`.

No production audio, transcripts, account data or vendor calls are needed to
develop or locally verify this path. Use only synthetic fixtures.
