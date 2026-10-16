# Deterministic shared speech for overlapping captures

Owner: dazheng. Requested 2026-10-16. Review by 2026-11-15.

## Behavior and scope

`CAPTURE_SHARED_SPEECH_MODE=off|shadow|on` defaults to `off`. An account is
selected by the union of `CAPTURE_SHARED_SPEECH_UID_ALLOWLIST` (comma separated,
default empty) and `CAPTURE_SHARED_SPEECH_PERCENT` (stable salted account bucket,
default 0). Invalid mode/percentage fails closed. Flags are evaluated at the call
boundary, not import time. Setting mode alone admits nobody.

Off preserves the incumbent path and adds no reads, writes or decision logs.
Shadow preserves incumbent grouping and adds at most seven decrypted reads per
completion to evaluate six overlapping candidates, including same-source pairs.
On replaces automatic capture grouping for selected accounts with the new
sentence rule, including the complementary desktop-call policy. It still writes
ordinary advisory cross-source overlap hints; clients do not collapse those hints.
All modes leave existing groups intact. No historical scan or backfill is run.

The new rule can group same-source/same-device, different-device and unknown-device
pairs. Device equality is neither evidence nor a reason to reject shared speech.
Every admitted pair must have positive wall-window overlap. The existing query
and six-pair budget remain bounded; query saturation is degraded evidence, not
proof that all candidates were considered. The longest observed windows are
checked first, with ID tie breaking.

The writer remains `database.capture_groups.join_capture_group`, with the same
transcript fingerprints, expected windows, sticky Separate exclusions,
deletion/discard/closed fences, 12-member cap, and refusal to bridge two existing
groups. It changes group metadata only. Transcript, summary, memories, tasks,
sharing and effects are retained independently. Separate reverses presentation
grouping and prevents regrouping with former members. It does not undo manual,
sync or smart merges. Switching off stops future decisions; it does not dissolve
groups already created.

Flutter/macOS collapse loaded members behind one representative and retain access
to every recording. A singleton loaded member remains visible. Pagination still
counts original records. On can leave new unsupported cross-source pairs as two
rows, and collapse new same-source duplicates; old groups do not change.

The hook runs after successful persistence in REST/sync/from-segments processing,
and after the durable fanout fence in live/Cloud Tasks finalization. Deploy the
same revision/config to Cloud Run backend, backend-sync, backend-sync-backfill,
backend-integration, GKE backend-listen and pusher. No client release is required.
Smart merge and EXP-003 Jev remain separate and unchanged.

## Matcher contract (overlap_shared_speech_v1)

1. Validate completed, retained captures and compatible lock partitions. Reject
   unknown/nonfinite/unplaced/out-of-capture timing. Select whole segments inside
   the wall intersection plus a five-second margin. A boundary-straddling segment
   cannot borrow all its words from outside the overlap.
2. Normalize Unicode NFKC, case, punctuation and straight/curly apostrophes. Ignore
   all speaker/own-voice labels. Require at least 30 words on each side in the
   intersection and token-set Jaccard at least 0.25. Jaccard alone never folds.
3. Compare lines whose wall starts differ by at most 15 seconds. Each accepted
   pair needs at least eight distinct words per line, six shared distinct words,
   two shared ordered bigrams, token Jaccard at least 0.5, and an ordered LCS of
   at least 60% of the longer line's tokens.
4. Assign lines one-to-one, require monotonic line order, and count each normalized
   sentence once per side. Require two distinct matched sentences, 20 distinct
   aligned words, eight distinct shared bigrams, start-time support spanning at
   least ten seconds on both sides, and at least 15 seconds of union duration of
   matched lines on each side. Gaps/silence and overlapping duplicate lines do not
   add duration. Line duration is transcript evidence, not acoustic ground truth.

Unknown layouts and overflow abstain, rather than truncate and claim a match.
Bounds per capture: 4,096 segments, 512 KiB text, 64,000 selected words, 4,096
characters and 90 seconds per selected segment. Pair work is capped at 16,384
line comparisons, 524,288 token-set operations and 262,144 LCS cells. The core is
pure CPU, uses no provider and persists no lexical fingerprint or transcript.
Changing cutoffs/version requires recalibration.

This deliberately misses noisy, clock-shifted, heavily resegmented or weakly
shared captures. It cannot determine the meaning of common background broadcast
audio from transcripts alone. Identical concurrent background speech is a safety
limitation to evaluate, not a claim of one semantic event.

## Calibration (2026-10-16, provisional)

Private inputs remain outside Git. Never copy cards, identifiers or text into
issues, PRs, logs or the knowledge base. Report aggregates only. David's `unsure`
labels are excluded from precision/recall and audited separately for folds.

Snapshot: 29 David labels (13 same, six different, ten unsure), 244 pair cards.
The card schema contains shared-axis starts but **no segment ends**. Consequently
the current card replay uses synthetic eight-second durations only as a lexical
proxy. Its precision/recall is **not calibration of the deployed duration gate**.
Do not activate on using that proxy. Original start/end exports have been requested.

| Data and class | Decisive n (same/different) | TP/FP | Precision (95% Wilson) | Recall (95% Wilson) |
| --- | --- | --- | --- | --- |
| David, start-only proxy, cross-source | 7 (5/2) | 3/0 | 100% (43.9–100%) | 60.0% (23.1–88.2%) |
| David, start-only proxy, same-source same-device | 12 (8/4) | 3/0 | 100% (43.9–100%) | 37.5% (13.7–69.4%) |
| David, start-only proxy, all | 19 (13/6) | 6/0 | 100% (61.0–100%) | 46.2% (23.2–70.9%) |
| September agent benchmark, cross-source | 52 (32/20) | 1/0 | 100% (20.7–100%) | 3.1% (0.6–15.7%) |
| September agent benchmark, same-source same-device | 43 (24/19) | 0/0 | undefined, no folds | 0% (0–13.8%) |
| September agent benchmark, same-source different-device | 1 (0/1) | 0/0 | undefined, no folds | undefined, no positives |
| September agent benchmark, all | 96 (56/40) | 1/0 | 100% (20.7–100%) | 1.8% (0.3–9.5%) |

No David different-device or unknown-device labels exist at this snapshot. No
proxy folds on ten unsure labels; eight excluded benchmark pairs also have no
folds. The benchmark uses actual segment ends, but enriched old same-scene labels
include adjacent events without overlap (38/104), truncated layouts and clock
errors. It is a stress set, not a prospective shared-sentences truth set. The
single benchmark accepted pair is insufficient evidence of useful recall or safe
fleet precision. Cases share captures, so Wilson intervals assume independence
that the actual sample does not establish; report them as descriptive only.

Two David negatives defeat a bag-of-words rule. Their window Jaccards are 0.398
and 0.653. The former has zero strong line pairs anywhere; the latter has 16
strong line combinations, all at least 35.8 seconds apart (best exact line pair
47.8 seconds apart). Neither has a strong line pair within 15 seconds. Both remain
separate. These observations do not establish a TV/background-audio diagnosis.

Thresholds favor false-fold avoidance: ordered, timed, distinct sentence evidence
and actual line duration are mandatory. Low global lexical overlap is allowed to
remain a false negative. Current evidence supports dark/shadow deployment only.
No claim of zero fleet false folds follows from zero observed labeled errors.

## Production rollout and rollback

Deploy dark, then land a separate runtime-env/chart config PR for shadow. Register
all selected hosts through the runtime-env renderer and validate pre-deploy checks.
Use the authorized workspace `bin/omi-deploy-prod` wait-eligible/cloud-run/listen
and approve-own sequence; resolve the currently qualified pusher promotion path.
Approve only runs dispatched by this owner. Capture served revisions/digests,
traffic, Helm revisions and rollback commands **before** every dispatch.

Watch request counts/5xx and fixed error signatures against the preceding equal
window on every touched service, readiness/restarts, and appearance of the new
`capture_shared_speech` line. Its JSON contains IDs, static categories/reasons,
numeric evidence, new verdict, incumbent ordinary would-join, existing-group
observation and write outcome; no text or lexical hashes. `current_would_join`
is the incumbent ordinary policy on checked discovery candidates, not proof a
transaction would commit; `already_grouped` is a separate observation. The
complementary-call policy is separately identifiable through existing call logs.
Exceptions emit fixed `outcome=error` without exception text. Aggregate/deduplicate
pair IDs locally; never paste raw production records.

After at least three clean shadow hours, compare counts by pair class and
incumbent/new verdict, bounds/timing abstentions, latency and error signatures.
Operations alone cannot prove accuracy. Before on, obtain real-end David
calibration, prospective labels including background audio, noisy segmentation,
different devices and clock drift, and a sufficiently precise independent false
fold bound. If safety is not established, stop at shadow and report the blocker.
Only then progress David on → 5% for at least three hours → 100%, watching every
step. No silent reduction of the observation window.

Prepared rollback: deploy the previous eligible commit through the same Actions
path, or land mode off / percentage 0 in runtime config and redeploy every touched
host. Existing group metadata is retained; Separate remains available. An image
rollback alone does not undo folds made while on. Exact service revision/digest
commands belong in the local owner report before each deployment.

After upstream transcription/attribution fixes, re-export original starts/ends,
re-read David's latest labels, freeze a versioned evaluation snapshot, and rerun
the unchanged matcher. Compare abstention reasons, precision/recall and labeled
background-audio negatives per class. Speaker attribution must remain irrelevant
to the decision. Use capture-component-disjoint held-out labels before tuning;
do not silently loosen cutoffs to recover old noisy positives. Requalify any
threshold/normalization/timing change in shadow before further activation.
