# Recording outcome: transcript and summary within minutes

The core promise is "a recording gets a transcript and a summary within
minutes". On 2026-11-16 from 18:50Z, summaries for finished recordings fell from
about 60% to about 10% for 21 hours and nothing paged. A co-deploy left the GKE
batch worker on an older merger build. It committed protocol-2 results without
the source marker, and the projector refused them (`immutable result binding
mismatch`). Projection is strictly ordered per owner, so every later recording
for that owner waited behind the refused head.

## Signals

| Rule | Reads | Pages when |
| --- | --- | --- |
| `omi-recording-outcome-fast` (critical) | `omi_batch_pipeline_recording_outcome_{finished,transcribed,summarized}_window_total` | transcript share < 0.60 or summary share < 0.10 for 10m, with at least 50 finished recordings in the cohort. NoData also pages, because it means the sampler is blind. |
| `omi-recording-outcome-slow` (warning) | the same gauges pooled over 6h | transcript < 0.70 or summary < 0.25 for 30m |
| `omi-batch-fresh-unprojected-share` (critical) | `omi_batch_pipeline_fresh_unprojected_ratio` | more than 10% of fresh results committed 10–20 min ago are still unprojected (at least 500 commits), for 10m |
| `omi-batch-projection-heads-blocked` (critical) | `omi_batch_projection_walk_stops_total{stop="blocked",progress="none"}` | at least 50 zero-progress turns stopped on a refused, non-privacy head in 10m, for 5m |
| `omi-batch-result-marker-skew` (warning) | `omi_fallback_total{component="sync_dispatch",from_mode="row_source_marker",to_mode="job_source_marker"}` | any increase in 30m: a merger host lags the result protocol |

**What the gauge counts.** The cohort is completed batch-live conversations
(`record_lane_owner=batch_live_v1`) whose `finished_at` falls in [now−45m, now−15m).

- *Transcribed* means `record_projection_revision > 0`. The live projection sets
  it in the same write that lands the transcript.
  - The revision counts projected units, each up to an hour of audio. A longer
    recording therefore counts as soon as its first unit lands.
  - The whole-record proof (the `transcribed` transition) is written only to the
    per-user `pipeline_ledger`. A count over conversations cannot join it.
  - A stalled head still leaves every recording queued behind it at revision 0,
    which is the failure this page exists for.
- *Summarized* means `summary_output_present == true`.
- *"Within 15 min"* on the tiles means every counted recording has had at least
  15 and at most 45 minutes to get its output. The share is presence at sample
  time, not a per-recording landing clock: a count cannot compare two fields of
  one document.

The denominator is every finished recording, so a stall in any stage lowers the
share. A latency histogram such as `omi_closed_to_summary_seconds` only observes
work that completes, so a stall gives it fewer samples rather than slower ones.

**Who samples it.** The serving maintenance leader on `backend-integration`
takes the sample once per minute, on the same lease as the fresh-delivery
guard. A failed count withdraws all three counts, and counts expire 180s after
the last success.

**Where the alerts read it.** The rules and tiles read `gmp-cloud-run`. The
in-cluster bridge does not import these families.

**Read budget.** Each sample is three count aggregations. Each costs
max(1, ceil(index entries / 1000)) reads, so a normal sample (about 200–900
recordings per cohort) costs 3 reads: about 4,300 reads/day per environment.
The planning envelope is 5,000 recordings per cohort, or 15 reads per sample
(21,600/day).

**Indexes.** The finished count uses the existing
`record_seal_repair_oldest_completed` index. The numerators use the new
collection-group composites `recording_outcome_summarized` and
`recording_outcome_transcribed`.

**Healthy levels.** These come from replaying the gauge every 60 s over 192,484
batch-live rows. The healthy stretch was 2026-11-15 10Z to 11-16 13Z.

| Share | Range | Median |
| --- | --- | --- |
| Transcript | 0.67–0.87 | 0.79 |
| Summary | 0.17–0.55 | 0.42 |

A summary within 45 minutes is not 100% even when healthy. Silent and discarded
recordings never get a summary, and the finish-to-summary median was about 15–20
minutes.

## When a rule fires: check in this order

1. **Is the deployed build the same everywhere?**
   - Check `OMI_BACKEND_RELEASE_SHA` on the revision receiving traffic for each
     of backend, backend-sync, backend-sync-backfill and backend-integration
     (`status.traffic`, not the service spec).
   - Check the GKE `prod-omi-batch-pipeline-worker` image tag. The worker also
     runs the ordered merger and deploys separately from Cloud Run.
   - A worker behind Cloud Run after a result-protocol change is the 2026-11-16
     cause. The marker-skew rule names it directly.
2. **Is projection refusing heads?**
   - Read `omi_batch_projection_walk_stops_total` by `stop`. The counter folds
     `blocked_<token>` to `blocked`, and the log line keeps the full token:
     `event=batch_projection action=owner_drain outcome=turn ... stop=blocked_<token>`
     on backend-integration.
   - `blocked_immutable_result_binding_mismatch` means a merger committed rows
     that the projector's binding check rejects.
   - `blocked_privacy_*` and `privacy_blocked` are the chronic privacy holds.
     They are excluded from the page.
3. **Is it the projection leg or earlier?**
   - A high fresh-unprojected ratio means transcripts exist and wait for
     projection.
   - A low transcript share with a normal fresh ratio points earlier: STT
     capacity, held units, or sealing. Use the batch stuck-state census and
     `backend/docs/runbooks/batch-language-delivery.md`.
4. **Summary only?** If transcript share is normal and summary share is low,
   the notes path is late. Compare `omi_fallback_total{component="conversation_notes"}`
   and the notes agent run rate.

## Safe actions

- **Roll every merger host to one build.** Roll the GKE batch worker first if
  it lags, then the Cloud Run services. For a refused head, the owner drain
  retries it, so no data repair is needed (#25597).
- **`BATCH_SOURCE_REUSE_ENABLED=false` on the sync intake services.** This stops
  new uploads from creating marker-protocol heads while a deploy is pending. It
  does not unblock heads that already exist (`sync-source-reuse.md`). To roll
  back, unset it.
- **Never delete results, staged audio, leases or ledger rows by hand.** Never
  set `BATCH_PIPELINE_RECORDING_OUTCOME_ENABLED=off` to silence a real breach.
  That stops the sample, and the fast rule then pages as blind.

## Activation

The fresh-unprojected and marker-skew rules read families that are already in
production. The recording-outcome gauges and the walk-stop counter need these
steps first, in order:

1. Create the two new indexes (`gcp_firestore_indexes.yml`).
2. Deploy backend-integration with this change.
3. Confirm the gauges in GMP:
   `count(omi_batch_pipeline_recording_outcome_finished_window_total{namespace="backend-integration"})`
   should equal 1, and `time() - max(..._sample_timestamp_seconds)` should stay
   under 120.
4. Only then provision the alert rules.

If the fast rule is provisioned before step 3, it pages as blind. That is the
intended reading of "no data".
