# Parakeet final-pass shadow (phase 1)

The streaming transcript remains the sole record. Live pusher WebSocket
finalization runs `finalize_persisted_conversation` on the standalone pusher
GKE pod via its pusher router; the durable Cloud Tasks fallback runs that same function on the
backend-sync Cloud Run host. The listen WebSocket itself dispatches these
finalization paths; it does not run the finalizer. After a finalization job owns
its lease, `finalizer.py` schedules a best-effort shadow pass in the *same
process* before `process_conversation`. The finalizer never awaits audio,
Parakeet, Redis, or the comparison write. Orderly shutdown cancels the tracked
coroutine, but an already running thread can continue until process exit. A
killed pod or Cloud Run revision can lose that in-flight work.
There is no shadow retry, so the result document can remain absent. Canonical
finalization remains durable and independent. Do not enable shadow on Cloud Run
until it has a separate durable dispatch. Two process-local slots bound
concurrency, and a shared Redis Lua reservation caps aggregate audio
milliseconds by UTC day. Redis failure denies the pass. The default cap is
zero.

## Controls

`TRANSCRIPTION_SHADOW_ENABLED` defaults false. `TRANSCRIPTION_SHADOW_KILL_SWITCH`
blocks admission even when enabled. `TRANSCRIPTION_SHADOW_UID_ALLOWLIST` is a
comma-separated exact UID allowlist; otherwise a stable UID hash is compared
with `TRANSCRIPTION_SHADOW_PERCENT` (default 0). The shared daily cap is
`TRANSCRIPTION_SHADOW_DAILY_AUDIO_HOURS` (default 0). Dev pusher is configured
with enabled=true, allowlist=`omi-release-probe`, percent=0, daily audio cap=1
hour, and kill switch=false. Dev backend-listen and backend-sync remain off;
the latter needs durable shadow dispatch before enablement. The local dev env
template remains off. No production values change. `TRANSCRIPTION_SHADOW_UPLOAD_GRACE_SECONDS`
defaults 70 so the pusher has time to flush its 60-second audio batch.
`TRANSCRIPTION_SHADOW_TIMEOUT_SECONDS` defaults 600; provider calls are also
bounded by the existing Parakeet client timeout. A worker checks the deadline
between slices. Background jobs are cancelled on orderly process shutdown.

Only conversations with `private_cloud_sync_enabled` and registered
`audio_files` qualify. The worker reads only chunk timestamps registered in
those files. Each chunk is decoded and clipped by its own timestamp; the dense
playback MP3 and the potentially drifting live `started_at` are never used to
position pass words. A long stored upload batch can contain a short utterance
followed by delivered digital silence. Before calling Parakeet, the worker
separates speech runs at at least one second of exact PCM zeroes and retains
300 ms of context at each edge. This avoids posting a mostly silent 60-second
batch for a few seconds of speech. It does not treat low-amplitude nonzero audio
as silence. Runs longer than 90 seconds use 10 seconds of overlapping context;
words spanning a cut are owned by the later request. The pass restores the
first-word offset removed by `postprocess_words`. A posted window is at most
90 seconds, below the 120-second provider limit and well below 100 MB for
PCM16 mono at 16 kHz. Each window gets
the offline-sync speaker matcher; conversation-wide clustering uses extracted
segment embeddings and enrolled voiceprints. No speaker embedding cache or
other canonical artifact is written by this path.

## Results and phase-2 gate

The private `users/{uid}/conversations/{conversation_id}/transcription_shadow_results/v1`
document stores only bounded scalar metrics: outcome, latency, captured
audio seconds, coverage, missing tail seconds, word-level edit distance to
the streaming transcript, word counts, owner-attributed seconds, speaker
counts, estimated clock offset, first stored chunk minus `started_at`, the v2 marker verdict, and remap success/safety. No transcript text,
UID label, audio, embeddings, or identity receipts are copied there. This
subcollection has one fixed-ID child and a fixed set of scalar fields, so its
size is bounded independently of transcript length. No backend API or client
reads it: the only production code reference is the shadow writer, and
conversation reads load only the parent document. The result transaction reads
the durable account-deletion marker and the conversation parent, refusing a
write once account deletion starts or the conversation is deleted;
the conversation delete path sweeps children again after deleting the parent
to catch a child committed during its first enumeration. Account deletion's
recursive user wipe removes results committed before its deletion marker.
Prometheus labels contain only the closed outcome vocabulary and, for remap
safety, a boolean verdict. The aggregate histograms for word distance,
owner-attribution delta ratio, and remap success are observed only when a pass
produces comparison metrics; a null word distance produces no distance sample.

Outcomes are `ok`, `failed`, `timeout`, `partial_audio`, `no_audio`, and
`skipped_budget`. A duplicate Redis reservation exits without counting or
writing a second result. A tail gap over five seconds or coverage below 95% is
`partial_audio`; this is expected on silence-timeout finalization when the
pusher's last upload has not arrived. Legacy Opus file durations can
underestimate decoded PCM; the worker atomically reserves any excess before
another provider call and stops if the daily cap is exhausted. Audio coverage uses stored chunk times
and the finalization wall-clock end; it is a measurement, not evidence that the
live transcript clock is correct. `word_distance` is a bounded WER-style edit
distance with the live words as denominator; it is null above 4,000 words or
when the live side has no words.

`segment_remap.py` aligns text in sequence and verifies an inferred clock shift
with unique, consistently shifted phrases. Time overlap candidates come from a
bounded interval index. Each annotation mapping needs ordered token coverage
in both directions: at least 65% of source tokens must occur in its mapped
targets, and unmatched tokens in each target may be at most 10% of that
target's tokens, rounded down. Fillers count as speech. This allows limited
ASR differences without requiring identical transcripts, while short targets
have no allowance for extra speech (including a trailing `yeah`).
`remap_safe` requires 100% of live segments mapped,
no ambiguous overlap, verified inferred offset, and successful annotation
remapping. The stored first-chunk minus `started_at` scalar lets operators
compare the physical audio origin with the text-derived shift (opposite signs
when both clocks refer to the same audio); an offset alone
cannot establish which clock drifted. The mapper expands source references and manual
speaker receipts over splits, rejects conflicting receipts on merges, and
rejects all concurrent target overlaps even when their text similarity differs,
rejects translations whose changed segmentation would duplicate or concatenate
whole translated sentences. Any unresolved, ambiguous, or unsafe annotation
sets `remap_safe=false`. Phase 2 must require safe remap as well as coverage and
owner-attribution parity before promoting a record. Shadow metrics do not
establish Parakeet's real-audio accuracy or a safe production capacity curve.

Durable shadow dispatch needs its own delayed Cloud Task, OIDC worker route,
idempotent lease/attempt receipt, retry policy, and runtime wiring. Reusing the
finalization task would couple retries and acknowledgement to canonical
processing, so this is a separate follow-up before a Cloud Run ramp.

## Dev operator readout

The normal dev pusher qualification probe sends the 17-word LibriSpeech fixture
eight times, or 136 spoken fixture words, followed by near-silence while the
socket stays open. It checks terminal finalization and the durable transcript
count within 80% to 120% of those eight sends, but does **not** enroll private-cloud sync or
check stored audio. Run its existing
`--alignment-scenario` with the fixed `omi-release-probe` token after the dev
pusher deployment. That scenario enrolls the isolated test account if needed,
creates one finalized conversation, checks that its private-cloud flag is set,
and rejects a durable transcript whose word count is outside 80% to 120% of
its two spoken 17-word fixture sends (34 expected). That scenario also delivers
five seconds of digital silence and pauses sending for four seconds; it adds
no other spoken audio. The receipt stores only live and
expected scalar word counts, so repeated text cannot silently pass the probe.
The scenario checks the candidate pusher's finalization-handoff log and waits for
registered chunk spans covering its speech windows. Its receipt
contains the generated `conversation_id` without transcript or audio content.
This is a test-account write; the coordinator runs it after deployment, not as
part of hermetic PR validation. The alignment mode rejects non-dev API
endpoints before any account request.

```bash
python3 backend/scripts/pusher_semantic_probe.py \
  --alignment-scenario --api-url https://api.omiapi.com \
  --bearer-token-file "$PROBE_TOKEN_FILE" \
  --deployment-receipt "$DEV_PUSHER_DEPLOYMENT_RECEIPT" \
  --project based-hardware-dev --namespace dev-omi-backend \
  --run-id "$RUN_ID" --output "$PROBE_RECEIPT"
conversation_id="$(jq -r '.conversation_id' "$PROBE_RECEIPT")"
backend/.venv/bin/python backend/scripts/read_transcription_shadow_result.py \
  --uid omi-release-probe --conversation-id "$conversation_id"
```

The readout script uses ADC and explicitly selects the `based-hardware`
Firestore data project used by the dev backend. It issues one masked document
get for `users/omi-release-probe/conversations/{conversation_id}/transcription_shadow_results/v1`
and prints only scalar fields; it has no write path. Exit code 2 with
`"metrics": null` means no result document yet. Wait at least the 70-second
upload grace plus processing time before treating absence as a missed pass.
Do not point this recipe at production serving or use another UID. A successful
alignment receipt proves stored audio was registered, but it does not prove
that the asynchronous shadow worker finished or that the entire audio tail was
covered; inspect `outcome`, `coverage`, and `tail_gap_seconds` in the result.

Use the **dev pusher Prometheus datasource** for these exact queries. The
histograms and counters are process metrics, so a pod restart can erase a
short window; the Firestore result is the per-conversation record. Prometheus
cannot select the allowlisted UID because no metric contains a UID label.

| Readout | PromQL |
|---|---|
| Outcomes, past 24 hours | `sum by (outcome) (increase(omi_transcription_shadow_total[24h]))` |
| Latency p95, past 30 minutes | `histogram_quantile(0.95, sum by (le) (rate(omi_transcription_shadow_latency_seconds_bucket[30m])))` |
| Agreement, mean word distance for complete audio | `sum(rate(omi_transcription_shadow_word_distance_sum{outcome="ok"}[30m])) / clamp_min(sum(rate(omi_transcription_shadow_word_distance_count{outcome="ok"}[30m])), 1e-9)` |
| Agreement, p95 word distance | `histogram_quantile(0.95, sum by (le) (rate(omi_transcription_shadow_word_distance_bucket{outcome="ok"}[30m])))` |
| Attribution parity, mean owner-seconds delta ratio | `sum(rate(omi_transcription_shadow_owner_delta_ratio_sum{outcome="ok"}[30m])) / clamp_min(sum(rate(omi_transcription_shadow_owner_delta_ratio_count{outcome="ok"}[30m])), 1e-9)` |
| Attribution parity, p95 delta ratio | `histogram_quantile(0.95, sum by (le) (rate(omi_transcription_shadow_owner_delta_ratio_bucket{outcome="ok"}[30m])))` |
| Remap success, mean mapped fraction | `sum(rate(omi_transcription_shadow_remap_success_rate_sum{outcome="ok"}[30m])) / clamp_min(sum(rate(omi_transcription_shadow_remap_success_rate_count{outcome="ok"}[30m])), 1e-9)` |
| Remap safety fraction | `sum(rate(omi_transcription_shadow_remap_safe_total{outcome="ok",safe="true"}[30m])) / clamp_min(sum(rate(omi_transcription_shadow_remap_safe_total{outcome="ok"}[30m])), 1e-9)` |

An empty series means no matching samples. For attribution parity, zero is
exact owner-seconds agreement; the ratio divides the absolute difference by
the larger of the two owner-second values or one second. A safe remap verdict
still requires adequate audio coverage and owner-attribution parity before
phase 2. None of these metrics establish ground-truth transcription accuracy.
