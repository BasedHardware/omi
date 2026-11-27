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

## Independent recovery comparison canary

Release verifies the serving `backend-sync` revision and the mobile build
together before exposing the hold cohort. With the flag on for a synthetic
test device, seal a Standard batch WAL and send it in the same process after
a delay. Expect `X-Omi-Upload-Journal-Recovery: fresh` and
`X-Omi-Upload-Recovered: 0`. Then seal a second WAL, terminate the app before
upload, and relaunch so the durable journal or index restores it. Expect
`X-Omi-Upload-Journal-Recovery: recovered` and
`X-Omi-Upload-Recovered: 1` on its first delivery. Both uploads should advance
the comparisons counter without advancing any mismatch series.

On an isolated serving revision, repeat the uploads with the reported
label flipped in each direction, then repeat with it omitted. Check the
`direction` series for `fresh_labelled_recovered`,
`recovered_labelled_fresh`, and `missing` respectively. A recognized hold
state with absent journal evidence also increments `missing` and leaves
the comparisons counter unchanged. Exercise the flag-off send with a
recovered WAL and check that it drains with its original recovered label
and contributes neither a comparison nor a mismatch. Keep deliberate
mismatches outside the production guard's selector because it queries
absolute counter values through process resets.

Evaluate the guard's expression at its last complete window, ending at the
minute aligned to the two-minute ingestion lag. Expect a present zero even
while idle. An empty result or a nonzero value trips custody.

```promql
max(max_over_time(omi_batch_pipeline_upload_recovery_label_mismatch_total{
  cluster="__run__",job="omi-cloud-run-application-metrics",location="us-central1",
  namespace="backend-sync",project_id="based-hardware",service_name="backend-sync"
}[10m]))
```

Check for a positive delta for both `fresh` and `recovered` in the same
complete ten-minute window. Start after a baseline scrape and confirm that
every traffic-serving revision exports the counter before exposure. The
guard's service-wide selector can return a zero from a single updated
exporter.

```promql
sum by (journal_state) (increase(omi_batch_pipeline_upload_recovery_label_comparisons_total{
  cluster="__run__",job="omi-cloud-run-application-metrics",location="us-central1",
  namespace="backend-sync",project_id="based-hardware",service_name="backend-sync"
}[10m]))
```
