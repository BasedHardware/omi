# Mobile batch upload latency by hold state

SCA-4372 needs per-state latency before Release enables the phone upload hold.
The first durable batch completion observes request-arrival-to-transcript
latency with the bounded `hold_state` label. The existing intake and content
ledger writes carry the field. Ordinary uploads add no Firestore operations,
and coalesced completions retain each original request's label and clock.

Release verifies labeled samples before the phone flag ramps from 0 to 5,
25, and 100 percent. During mixed backend revisions the guard selects
explicit hold states, which use the new 360-second bucket. When the client
provides a valid hold age on a new batch admission, sync also observes it in
`omi_batch_pipeline_upload_hold_age_seconds`. The rollback guard adds
phone-age p90 to server-publication p90 per state and compares the sum with
the hold window plus 300 seconds. The age adds no Firestore field or operation.

[Request header contract](../../listen_pusher_pipeline.mdx) ·
[Canary measurement rules](../../runbooks/batch-upload-coalescing.md#measurements-and-first-canary)

Follow-up: `X-Omi-Upload-Recovered: 1` adds a bounded `recovered="true"`
label to the hold-age and publication-latency histograms. Other inputs are
`recovered="false"`. True rides on existing intake and completion metadata,
including coalesced originals. No additional Firestore operations are required.
