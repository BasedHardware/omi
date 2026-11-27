# Refusing an exact WAL retry before multipart

The first body still goes to Cloud Run. On a verified capture-manifest upload the server can issue a short-lived handle when the record router writes a conversation wait for missing jobs or a pending reservation. The HMAC binds the UID, install, target, complete filename and SHA-256 claims, conversation-wait protocol and absolute expiry. Updating either service or the client alone leaves multipart admission available. See the [sync admission contract](../../listen_pusher_pipeline.mdx#sync-admission-no-audio-clips-and-bounded-refusals).

## Which requests can save time

The ordinary POST parses multipart, filters empty and torn clips, canonicalizes filenames and checks for future-clock recovery before consulting its conversation memo. Only after that come cutover, lane and allowance checks, lease acquisition, staging, recovery, verification of the manifest against the bytes, repair ownership and record routing. Issuance requires an unchanged filename list, checked file digests and an explicit, device-bound conversation. An early conversation-memo hit already returned before digest verification. Such a response cannot issue a handle.

The mobile recording gate persists a minimum 30-second wait plus jitter. The original conversation memo expires after 30 seconds. An isolated WAL therefore yields **zero eligible retry-seconds** on its own memo. Another full attempt for that conversation can populate a new live memo while the 120-second identity handle is valid. Mobile piggybacks the handle on the manifest call it already makes. Provenance, lease renewal, immutable claim and event still execute there. Only a live hint invites the separate authenticated PUT on the upload URL. It repeats the ordinary memo allowlist, handoff bypass and receipt check. The PUT reads metadata and issues no renewal or handle. Expiry, absence, dependency failure and incompatible versions return the client to its ordinary upload. A cold client discards its hint and retains its existing WAL and cooldown.

Coverage waits contribute **zero eligible seconds** in this implementation. Their 300-second memo sits after an archive callback that can write original bytes and renew custody. A hit can also require a partial-record wake. Receipt discovery, settlement, handoff and privacy decisions can supersede the negative. Other exclusions include unnamed targets, non-manifest traffic, changed or mixed empty bundles, repairs, clock recovery, first attempts, other refusal reasons, and older clients. The fleet distribution of request time across these cases is unmeasured.

## Replay and overhead

From the repository root on M1, run the two focused suites after the usual component bootstrap.

```sh
(cd app && omi-heavy run --wait 120 -- gtimeout 180 flutter test --no-pub --reporter expanded test/unit/wal_retry_manifest_transport_test.dart)
(cd backend && omi-heavy run --wait 120 -- gtimeout 180 bash test.sh tests/unit/test_wal_retry_precheck.py tests/unit/test_sync_record_coverage_wait_memo.py)
```

The mobile replay measures server receive and synthetic service time with a 256 KiB WAL, loopback HTTP and a 2 MiB/s body-service assumption. It prints bytes and microseconds for an eligible refused POST and the replacing PUT. Their difference is the modeled saving for **one invited hit**. The replay omits production authentication, Redis, Firestore, WAN and manifest processing latency. Both arms already pay for a manifest. The candidate adds one local identity digest over metadata, HMAC checks, and at most one hint lookup per eligible manifest. Every invited PUT adds an authenticated request, a memo read and, on a memo hit, the receipt guard. A proceed or error pays for both the PUT and full POST.

## Fleet readback after release

Use the same closed UTC 24-hour boundaries for all counts and times. Record the serving revisions of the manifest and sync handlers, client build adoption, and whether PUT reaches backend-sync. Group existing request latency by service, method, route and outcome. Sum distribution counts multiplied by their means (or sum request latency directly). Use the sum across **all backend-sync requests** as the denominator. The conservative numerator is all PUT seconds plus POST seconds attributable to typed pending. Include PUTs preceding an acceptance, errors and timeouts. For an upper bound include all unattributed POST 503 seconds. Report absolute seconds, both ratios and the incremental manifest time on whichever service handles it. The fleet target is below 10%.

Use approved fixed-label wait-answer and memo-hit counters to distinguish conversation and coverage volume. Counts alone cannot attribute duration. Break down compatible and legacy builds where existing aggregates support it. Include total 503s, POST 503s per accepted POST (200 + 202), refused attempts per accepted audio-hour, accepted audio-hours, peak active instances, and maximum hourly mean. Compare first-refused cohorts at 1 and 24 hours for acceptance, p50/p95 age at acceptance, oldest pending age and still-pending audio. Report missing dimensions as unmeasured. Do not derive a fleet hit rate from the replay or a two-minute all-503 sample. Worsening retry age or acceptance precludes a savings claim.
