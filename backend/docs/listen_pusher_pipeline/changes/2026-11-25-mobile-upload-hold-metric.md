# Mobile batch upload latency by hold state

SCA-4372 needs per-state latency before Release enables the phone upload hold.
The first durable batch completion observes request-arrival-to-transcript
latency with the bounded `hold_state` label. The existing intake and content
ledger writes carry the field. Ordinary uploads add no Firestore operations,
and coalesced completions retain each original request's label and clock.

The rollout guard reads `omi_batch_pipeline_upload_hold_age_seconds` for
the phone side. It uses the client's clock at multipart send and samples
each fresh batch admission, so it pairs with the server publication metric
without including upload transit in the phone age. The general
`omi_sync_seal_to_accept_seconds` family continues to diagnose waits across
all traced uploads using server receive time and the upload gate.

The phone-age histogram uses the same bounded `gate` from
`X-Omi-Upload-Trace`. A missing or malformed trace maps to `other`. Exclude
`gate=~"offline|retries_exhausted"` on the phone side of the guard and chart
those waits separately. The gate is the last observed blocker, so it is
diagnostic context rather than a complete history of the wait.

[Request header contract](../../listen_pusher_pipeline.mdx) ·
[Canary measurement rules](../../runbooks/batch-upload-coalescing.md#measurements-and-first-canary)

Follow-up: `X-Omi-Upload-Recovered: 1` adds a bounded `recovered="true"`
label to the hold-age and publication-latency histograms. Other inputs are
`recovered="false"`. True rides on existing intake and completion metadata,
including coalesced originals. No additional Firestore operations are required.

## Pre-ramp latency receipt

Keep the public flag at 0% while Release verifies the serving sync and
publication revisions with the rollout mobile build. For each hold state
(`fg60`, `bg300`, `fg_preview300`), exercise a synthetic fresh held WAL and
wait for durable transcript publication. Verify that
`X-Omi-Upload-Hold` and `X-Omi-Upload-Hold-Age-Ms` produce a positive count
increase on `omi_batch_pipeline_upload_hold_age_seconds`, and that
`omi_batch_pipeline_upload_to_transcript_seconds` advances under the same
`hold_state` and `recovered="false"`. Check that the phone-age series has the
expected `gate` label. Record the app build, serving revisions, measurement
window, and per-state count deltas in the SCA-4508 ramp receipt. A missing
series or one with no new samples leaves that state unverified.

For the absolute latency guard, use explicit hold states, filter both
histograms to `recovered="false"`, and select the labeled phone series with
`gate=~".+",gate!~"offline|retries_exhausted"`. Compare the sum of phone-age
p90 and server-publication p90 per state with the state's hold window plus
300 seconds. The existing SCA-3891 paired seal-to-transcript p90 comparison
against matched unheld traffic is also required before 5% public exposure.

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
