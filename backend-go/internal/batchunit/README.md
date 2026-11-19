# batchunit: the reference job kind

Transcribes one unit of an owner's batch, in the owner's order, paying once. Copy this package's
shape when you add a kind.

## Shape

| File | Holds | May import |
| --- | --- | --- |
| `unit.go` | Types and pure decisions: validation, how a job is built, when work is already done | standard library, `internal/queue` types |
| `ports.go` | The interfaces this kind needs from outside: `Speech`, `Accounts`, `Observer`, `Keys` | `internal/queue` |
| `service.go` | The shell: `Admit`, and the queue handler `Work` and `Exhausted` | `internal/queue` |

The binary supplies the port implementations. Today they come from
`internal/conformance/stubapi`; swapping in real clients changes `cmd/`, not this package.

## Rules and the test for each

| Rule | Test |
| --- | --- |
| A unit needs an id, an input (empty is allowed, absent is not) and an order time | `TestValidateNeedsIDInputAndOrderTime` |
| The owner is both tenant and ordered lane, so an owner's units run one at a time in order | `TestNewJobPutsTheOwnerInItsOwnOrderedLane`; lane behaviour in `internal/queue` `TestOrderedLaneProperty`, `TestFairnessAndOrderedHold` |
| An invalid unit is never enqueued | `TestNewJobRejectsAnInvalidUnit` |
| A stored result is never paid for again, including after exhaustion | `TestDoneOnlyWhenAResultIsStored`; end to end in the conformance kit's batch cases |
| A corrupted stored input parks the job instead of looping | `TestInputRejectsAStoredValueThatIsNotAString` |
| Admitting the same unit twice returns the first job | `internal/queue` `TestEnqueueIdempotencyProperty`; conformance kit `test_batch_order` |

## Adding a step to this kind

1. Add the decision to `unit.go` as a pure function, with a table test.
2. If the step needs something external, add a method to a port (or a new port) with its
   idempotency and charging contract in the comment.
3. Call it from `service.go` inside `r.Guard`, save progress with `r.Save`, and turn any error
   into an outcome with `queue.FromError`.
4. Add the row to the table above.
