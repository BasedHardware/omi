# v3 TestFlight Finish-to-Home readback

SCA-4489 measures deliberate v3 TestFlight Finishes. Before the WAL snapshot
starts, the app persists a content-free `finish_cut` event in its dedicated,
authenticated outbox and stamps the same operation token and cut time on the
Finish API request. The outbox retries the event independently, so a cut that
never reaches the Finish API remains in the denominator as unmatched. Event
retries and the API header share the same opaque finish key and are deduplicated
in readback.

An older beta request without the operation header is only eligible when a
committed server-side manual-end marker proves the deliberate Finish. Those
legacy samples use `unknown` source and the server receipt time (`server_cut`),
which is a lower bound on elapsed time. An untagged request without that proof
is excluded.

When v3 is active, TestFlight Home uses `GET /v1/conversations` and suppresses
the compact `/v1/home/feed` reader. Summary readiness is logged only from the
actual Home response, after ownership and acknowledged-episode projection,
list filtering, and redaction. A row must still be a completed, settled v3
manual-end card with an overview or rendered note section. An empty transcript,
preview, placeholder, hidden, merged, or locked card cannot satisfy the check.
The reconcile mapping uses the cut that actually closed the window, including
when the closing recording is silent and its predecessor supplies the speech.
An unbound Finish, a client-only cut, and a cut with no qualifying Home card
remain unmatched.

Route is `held` when a predecessor holds the cut, `fast` after a successful
fast transcript write, `batch` when ordinary batch admitted it and there is no
earlier qualifying fast or hold observation, or `unknown`. Events carry
opaque, domain-separated HMACs in restricted logs. The readback returns
aggregates and never prints join keys, raw identifiers, or user content.

## Rollout and query

Deploy through the normal release flow. The client and serving backend must
both include the dedicated Finish-cut outbox and `/v1/telemetry/v3-finish-cuts`
route. Once the relevant TestFlight build is distributing, enable
`CONVERSATIONS_V3_FINISH_HOME_SLI=on` together on the serving Finish API, cut
ingest, batch admission, v3 builder/notes, and Home reader runtimes. Validate a
controlled app-button and pendant Finish against the live TestFlight Home
response, including ownership and acknowledged-episode filtering, before
setting the cohort start. Set the flag to `off` on those runtimes to stop new
observations. Keep a record of every serving backend revision and the TestFlight
build over the cohort window.

From the repository root with the read-only production identity, supply UTC
RFC3339 bounds. Use the same deployment's established project for all
producers, including any GKE workers. `OBSERVED_THROUGH` must be at least
60 seconds after `COHORT_START + 24h`. Run after the log ingestion delay and
extend the observation horizon if late matches matter.

```bash
set -o pipefail
source ~/.local/bin/gcp-agent-env.sh ro-prod
: "${LOG_PROJECT:?use the serving production logging project}"
: "${COHORT_START:?UTC timestamp at or after full rollout}"
: "${OBSERVED_THROUGH:?UTC timestamp at least 24h 60s after cohort start}"

gcloud logging read \
  "(textPayload:\"event=v3_finish_home_sli \" OR jsonPayload.message:\"event=v3_finish_home_sli \") AND timestamp>=\"$COHORT_START\" AND timestamp<=\"$OBSERVED_THROUGH\"" \
  --project="$LOG_PROJECT" --limit=25000 --format=json |
  python3 backend/scripts/finish_home_readback.py \
    --cohort-start "$COHORT_START" --observed-through "$OBSERVED_THROUGH"
```

The readback takes a half-open 24-hour cut cohort. It deduplicates cuts and
bindings, gates legacy candidates on committed manual-end proof, joins the
first qualifying card, and reports totals, within 60 seconds, late, unmatched,
timing unknown, and the p95 for each route and source. Client-only cuts with no
API binding are included as unmatched. An older-build lower bound can establish
a late finish. A lower bound inside 60 seconds remains timing unknown. The
all-Finish p95 is reported only when the nearest rank is determined despite
missing and unknown observations. Matched client-cut p95 and coverage describe
the observed subset. An export reaching 25,000 matches needs complete disjoint
reads before it can be used.

Post the aggregate report, serving revisions and bounds on SCA-4434, even
when the target is missed. If the serving build mix or ingest coverage leaves
the fleet denominator incomplete, include that instrumentation gap with the
readback.
