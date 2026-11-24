# batchunit: the reference job kind

Transcribes one unit of an owner's batch, in the owner's order, paying once and never losing a
result it paid for. Copy this package's shape when you add a kind.

## Shape

| File | Holds | May import |
| --- | --- | --- |
| `unit.go` | The kind's declaration, its types and its pure decisions: validation, how a job is built, what a stored input and a receipt look like | standard library, `internal/queue` types |
| `ports.go` | The interfaces this kind needs from outside: `Speech`, `Results`, `Accounts`, `Observer`, `Keys`, each with its contract | `internal/queue` |
| `service.go` | The shell: `Admit`, and the queue handler `Work` and `Exhausted` | `internal/queue` |

The binary supplies the port implementations. `internal/adapters/batchdocs` is the Firestore
`Results`; the conformance kit uses `internal/conformance/stubapi`. Swapping one for another
changes `cmd/`, not this package. `tools/archcheck` enforces the import column.

## Rules and the test for each

Pure rules are tested as tables in `unit_test.go`. Handler rules run on real workers against
Postgres through `internal/queue/queuetest`, in `service_test.go`.

| Rule | Test |
| --- | --- |
| A unit needs an id, a source reference and an order time | `TestValidateNeedsIDSourceAndOrderTime` |
| The owner is both tenant and ordered lane, so an owner's units run one at a time in order | `TestNewJobPutsTheOwnerInItsOwnOrderedLane`, `TestAnOwnersUnitsRunInOrderOneAtATime` |
| The job row stores a reference to the input, in a fixed format-1 shape | `TestStoredInputIsAReferenceThatRoundTrips` |
| An invalid unit is never enqueued | `TestNewJobRejectsAnInvalidUnit` |
| Only a source with a reference is a readable input; null, `{}` and other types are not | `TestInputRejectsAnythingButASourceWithAReference` |
| Only a complete receipt counts as done; `{}` and a half receipt do not | `TestStoredOnlyAcceptsACompleteReceipt`, `TestCheckpointRefusesAnIncompleteReceipt` |
| Every step and cause the handler uses is declared | `TestDeclarationListsEveryStepAndCause` |
| A unit is charged once, its result stored, and the row holds a receipt and no transcript text | `TestUnitIsTranscribedStoredAndChargedOnce` |
| A retry sends the same operation and is not charged again | `TestALostVendorResponseIsRetriedWithTheSameOperationAndChargedOnce` |
| A result that was paid for is recovered after the attempt budget runs out, not parked | `TestAPaidResultIsRecoveredWhenTheLastAttemptCouldNotRecordIt` |
| With nothing committed at the vendor, an exhausted unit parks with its cause | `TestAUnitTheVendorNeverCommittedParksWithItsCause` |
| An owner being deleted is held before anything is paid, and its other units are not tried | `TestAnOwnerBeingDeletedIsHeldBeforeAnythingIsPaid` |
| Admitting the same unit twice returns the first job with the first input | `TestAdmittingAUnitTwiceReturnsTheFirstJob` |
| A corrupted stored input parks the job instead of looping | `TestACorruptedStoredInputParksInsteadOfLooping` |

## Adding a step to this kind

1. Add the decision to `unit.go` as a pure function, with a table test.
2. Add the step to `Declaration`, and any new cause.
3. If the step needs something external, add a method to a port (or a new port). It takes a
   `queue.Guarded`, and its comment states what it guarantees about repeats and charging.
4. Call it from `service.go` inside `r.Guard`, with `g.Operation(step)` as its identity. Save a
   receipt with `r.Save`, never the payload. Turn any error into an outcome with `queue.FromError`.
5. Teach `Exhausted` how to find out whether the step already happened.
6. Add the rows to the table above.

## Changing the stored shapes

`stored` and `Receipt` are what old rows mean. To change either, add a new `Format`, declare both
formats in `Declaration` until no job in the old one remains, and decode by `Job.Format`.

## Batch-shadow funding inputs

Intake supplies the custody deadline and audio duration from the existing retention record. The account adapter returns a positive, monotonically increasing generation for every change between exhausted and funded, including grants and effective period boundaries. An unversioned account leaves the stored observation intact. BYOK and paid-result recovery are trusted intake dispositions. The speech adapter receives the frozen route and BYOK flag. Recovery calls only `Recover`.

During replay, the driver sends an owner notification by HTTP to `POST /v1/batch/{owner}/entitlement-changed`. The conformance binary obtains the generation, exhaustion and source timestamp with one `GET /accounts/{owner}` against `STUB_URL`. Billing subscription changes, referral-grant changes and UTC usage-period rollover share this invalidation. The repository has no live publisher from those authorities to this endpoint.

Set `GO_BATCH_ENTITLEMENT_CONDITION_HOLD=true` on the batch-shadow jobd to enable condition holds. Every minute it sweeps due custody deadlines and claims up to 100 due owners, reading the account once per owner. Each owner is due hourly. For rollback, set the flag to `false` (the default) and restart shadow jobd. Its maintenance pass returns outstanding units to their ordered lanes with their custody deadlines and refusal generations intact. Workers apply the existing tenant-wide time hold with a five-minute retry until they observe a newer funded generation. Wait for format-2 work to settle, quiesce shadow intake, and revert the change. Old workers only understand format 1.

The p99 funding-change-to-durable-release target of 60 seconds is a test target. Shadow qualification requires a `READBACK:` with the event count, measurement window and p99 from real funding changes.
