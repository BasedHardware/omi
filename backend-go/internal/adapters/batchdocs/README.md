# batchdocs: transcription results in Firestore

Implements `batchunit.Results` on `internal/platform/docstore`. It is the reference for an
adapter that keeps tenant data. The tests need the Firestore emulator
(`scripts/with-firestore.sh`); the last one also needs Postgres.

One document per unit at `users/{owner}/batch_unit_results/{unit}`, with fields `operation`,
`transcript` (encrypted with the owner's key) and `stored_at`.

## Rules and the test for each

| Rule | Test |
| --- | --- |
| The transcript is stored encrypted with the owner's key; the receipt is its path | `TestPutStoresTheTranscriptEncryptedAndReturnsItsLocation` |
| A repeat of the same operation returns the first receipt and writes nothing; a different operation for the same unit fails | `TestPutIsIdempotentPerOperationAndRefusesADifferentOne` |
| An owner with a deletion marker gets nothing written, and the tenant is held | `TestPutHoldsAnOwnerBeingDeletedAndWritesNothing` |
| A caller without a live guard writes nothing | `TestPutWithAnEndedGuardWritesNothingAndAborts` |
| A write still in flight after its worker's database session died and the tenant was erased is refused by Firestore | `TestAWriteThatOutlivesItsGuardIsRefusedByFirestoreAfterAnErase` |

## What a new adapter for tenant data must copy

- Write only inside `docstore.Fenced`. Never use a Firestore client directly.
- Read before you create, and compare the stored operation, so a repeat is a no-op.
- Return every failure through `queue.Classify` with the outcome it means: hold for an owner
  being deleted, retry for a transient fault, fail for one that will repeat.
- List the causes in `Causes()` so the binary can declare them with the kind.
