# speech

Modulate Velma-2 is the first pre-recorded adapter. On Python's built-in batch route,
Parakeet handles supported languages on the GPU and Modulate is the external vendor
for the rest. See `backend/utils/batch_pipeline/provider_stt_admission.py`,
`backend/utils/batch_pipeline/vendor_route_contracts.py`, and
`backend/utils/stt/{modulate_batch,pre_recorded}.py`. The calling family selects the
route, resolves audio to WAV or FLAC, and supplies its declared step and language
fallback. The adapter's input cap is 200 MB, matching `_MAX_UPLOAD_BYTES`
in `backend/routers/stt.py`. Velma detects the language itself, as in the Python
client. Speaker diarization defaults to on, and callers can set
`DisableDiarization` to opt out. The adapter returns timed turns and preserves
Python's batch speaker-fallback signal.

Python's pre-recorded Modulate route uses the managed Modulate credential, including
for enrolled BYOK owners. An explicitly enabled owner-key route takes an already
validated key from the caller and does not fall back to the managed key. The adapter
does not implement credential enrollment, vendor failover, or production wiring.

## Operation and billing

The [synchronous batch endpoint](https://docs.modulate.ai/api-reference/stt/batch)
has no documented idempotency header, client reference, or job lookup. The adapter
uses `g.Operation(step)` locally as the key under
`users/{owner}/speech_modulate_operations/{operation}`. A fenced Firestore
transaction reserves each attempt, and a second fenced read checks the shared
deletion marker immediately before the POST. Modulate cannot refuse a late write,
so an erase that starts between the pre-POST fence check and dispatch can still
result in the owner's audio reaching the vendor. The adapter encrypts the
successful reply with the owner's key and commits it through the same fence.
Separate adapter instances sharing the store return the committed reply, including
silence. Vendor origins require HTTPS, with HTTP allowed for literal loopback
test addresses. Redirects and automatic POST replay are disabled. Records belong to the
user subtree and must survive for as long as the operation can be replayed.

If execution stops between reservation and result commit, the adapter cannot
distinguish never sent from paid with a lost reply. It leaves the reservation in
place and refuses another upload. Callers must keep the vendor route fixed for
the operation. `Recover` reads successfully committed replies;
otherwise it returns `ErrNotCommitted` for operator reconciliation. This policy
favors at-most-once charging over guaranteed completion. The stored response
and language fallback are capped at 700 KiB before encryption to fit one
Firestore document. A larger reply follows the same unresolved path.

An ordinary managed HTTP 429 with a complete error body lets the queue back off
and reserve a new attempt under the same operation. Budget refusals remain
terminal. The adapter scans up to 64 KiB for budget markers. An incomplete body
without a recognized budget marker leaves a managed 429 unresolved. Older
terminal rate-limit records stay closed because the old response cap could have
hidden a budget marker.

## Queue error classes

| Cause | Meaning |
| --- | --- |
| `speech_owner_key`, `speech_owner_quota` | Missing or malformed owner key, or vendor auth, credit, or throttle refusal on the owner-key route |
| `speech_managed_key`, `speech_provider_budget`, `speech_provider_rate_limit` | Managed key missing or refused, managed provider credits depleted, or managed provider throttling |
| `speech_input`, `speech_invalid_reply` | Missing, oversized or vendor-rejected input, or a malformed or contradictory success response |
| `speech_unresolved` | Reserved operation without a committed result, including transport loss, oversized replies, or uncertain vendor statuses |
| `speech_store_unavailable`, `speech_store_rejected` | Transient or permanent operation-store failure |
| `speech_owner_deleting` | The owner deletion fence blocks the call |

The adapter retries confirmed managed throttling and transient store failures,
returns deterministic failures for other vendor outcomes and store rejections,
and holds on owner deletion. Queue lease loss
propagates to the caller. Errors contain closed causes, with no vendor payload or key.

## Rules and tests

| Rule | Test |
| --- | --- |
| Multipart FLAC, default diarization, managed auth, timestamps, partial turns, speaker fallback, automatic language, and result reuse across instances | `TestModulateUploadsOnceAndRecoversPartialTranscript` |
| Multipart WAV, explicit diarization opt-out, owner auth, and recovery of silence | `TestModulateRecoversValidSilence` |
| A lost response blocks further POSTs, even from a new adapter instance | `TestModulateLostReplyNeverUploadsAgain` |
| A redirect triggers neither a follow-up request nor another POST | `TestModulateDoesNotFollowOrReplayRedirects` |
| A guard ending during the upload propagates lease loss and prevents the result from being committed | `TestModulatePropagatesLeaseLossBeforeFinishing` |
| Concurrent adapters sharing one operation send one POST | `TestModulateConcurrentReservationsSendOneUpload` |
| The operation record encrypts the reply, is owner-scoped and respects owner deletion | `TestModulateStoresEncryptedReplyAndFencesDeletedOwner` |
| Deletion activated after reservation blocks the POST | `TestModulateFencesDeletionActivatedAfterReservation` |
| HTTP is permitted only for literal loopback origins | `TestModulateRequiresTLSOutsideLoopback` |
| A complete managed throttle refusal can be retried under the same operation | `TestModulateRetriesConfirmedManagedRateLimit` |
| Budget markers beyond 4 KiB are recognized and truncated managed throttles remain unresolved | `TestModulateSeparatesOwnerAndManagedRejections` |
| Owner auth and quota failures have distinct causes, including on replay | `TestModulateSeparatesOwnerAndManagedRejections` |
| Malformed and oversized successes block replay and have no recoverable result | `TestModulateInvalidAndOversizedRepliesNeverUploadAgain` |
| Missing or malformed owner credentials never fall back to managed auth, and a missing guard prevents any call | `TestModulateRequiresGuardAndCredentialBeforeUploading` |
| Invalid and contradictory vendor replies cannot settle as silence | `TestModulateSilenceRequiresACoherentReply` |
| Top-level text and duration are used only to validate silence | `TestModulateOnlyUsesTopLevelMetadataToValidateSilence` |
| Language voting breaks ties on duration and then first occurrence | `TestModulateLanguageUsesWordCountThenDurationThenFirstSeen` |
