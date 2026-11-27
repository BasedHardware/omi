# conversations

`Store.Load` and `Store.ApplyFinalization` are guarded ports for finalization workers.
They address `users/{owner}/conversations/{id}` via `internal/platform/docstore`.
Consumers register `Causes()` with their queue kind and acquire a fresh load before
recomputing a result after `ErrChanged`. The load token compares stored field values.
The transaction rechecks those values and the account deletion marker before the update.

| Python storage behavior | Emulator test |
| --- | --- |
| Legacy list, zlib bytes, encrypted JSON and encrypted zlib hex decode in stored order | `TestLoadDecodesPythonInlineFormats` |
| Missing speech defaults to an empty list. Failed authentication, corrupt payloads and pointers are distinguishable from an empty list | `TestLoadDistinguishesEmptyPointerAndUnreadableTranscripts` |
| Transcript storage sidecars require identity or consent handling before use. The port withholds them | `TestLoadDoesNotReturnStorageIdentitySidecars` |
| Processing-result merge writes status and finalization status as strings, discarded as a boolean, structured title and overview as map leaves, and finished time and coverage as Firestore timestamps | `TestApplyFinalizationMatchesPythonFieldMask` |
| A finalization commit advances the Home source version, dirties the conversation link and invalidates Home readiness while preserving link ownership and other control fields | `TestApplyFinalizationMatchesPythonFieldMask`, `TestApplyFinalizationPreservesOwnerOverrides` |
| User title, user overview and explicit keep decisions take precedence over generated output | `TestApplyFinalizationPreservesOwnerOverrides` |
| Legacy rows can acquire structured fields. The v3 summary title lock preserves the stored title | `TestApplyFinalizationAddsStructuredFieldsToLegacyRows` |
| A stale input, lock or deletion fences a late result. A writer cannot recreate a missing document | `TestApplyFinalizationRefusesStaleMissingAndProtectedRows` |
| Private rows fail with `ErrRestricted` and `queue.Fail(CauseRestricted)` on load and update | `TestLoadRefusesPrivateRows`, `TestApplyFinalizationRefusesStaleMissingAndProtectedRows` |
| A bounded payload can hold the transcript and structured notes. A notes update replaces the generation and writes its Home receipts in the same commit | `TestLoadPythonPayloadAndWriteNotes`, `TestApplyFinalizationRepacksSpilledStructured` |
| A payload update over the atomic budget holds finalization without changing the current generation or its receipts | `TestApplyFinalizationHoldsOverBudgetPayloadWithoutChangingIt` |
| An active account deletion marker prevents repacking an existing payload | `TestApplyFinalizationFencesSpilledNotesDuringAccountDeletion` |
| Reopening a dead-letter row requires an explicit restore path. This port refuses queued, leased and BYOK transitions | `TestApplyFinalizationRefusesDeadLetterReopen` |
| If terminal lifecycle fields are refused, content fields and their Home receipts still commit | `TestApplyFinalizationCommitsContentWhileRefusingLifecycle` |
| Only the guarded owner can read and update. An active deletion marker holds that owner | `TestDeletionMarkerAndGuardFenceReadsAndWrites` |

For a refused terminal transition, `ApplyFinalization` preserves `status`,
`finalization_status` and `discarded`, then returns `ErrLifecycleRefused` with
`queue.Fail(CauseRejected)` after the transaction succeeds. A lifecycle-only
refusal leaves the document and Home receipts untouched. Invalid status values
return `ErrStatus` without writing.

The wire fixture comes from the Python transcript encryption/compression helpers,
the processing-result field mask and Firestore emulator snapshots. Regenerate it
with `scripts/with-firestore.sh ../backend/.venv/bin/python internal/adapters/conversations/testdata/generate.py`
from `backend-go`. It contains synthetic speech and uses a public fixture key.

This is the conversation document field adapter. Worker rollout also needs the
Python lifecycle effects (including summary debt and derived projection building),
explicit terminal restore, and any identity sidecar hydration or user-correction projection
required by the consumer. For object-lake transcripts, `ErrPointer` lets the caller
route to an existing reader. A Go reader needs a lane B platform interface that
validates owner, class and bucket, uses consent and key custody, and distinguishes
absent, shredded, corrupt and temporarily unavailable blobs.
