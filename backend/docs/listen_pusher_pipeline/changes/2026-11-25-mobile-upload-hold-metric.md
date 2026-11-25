# Mobile batch upload latency by hold state

SCA-4372 needs per-state latency before Release enables the phone upload hold.
The first durable batch completion observes request-arrival-to-transcript
latency with the bounded `hold_state` label. The existing intake and content
ledger writes carry the field. Ordinary uploads add no Firestore operations,
and coalesced completions retain each original request's label and clock.

Release verifies labeled samples before the phone flag ramps from 0 to 5,
25, and 100 percent. During mixed backend revisions the guard selects
explicit hold states, which use the new 360-second bucket. Phone wait is
measured separately from server publication latency.

[Request header contract](../../listen_pusher_pipeline.mdx) ·
[Canary measurement rules](../../runbooks/batch-upload-coalescing.md#measurements-and-first-canary)
