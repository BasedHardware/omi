# Batch replay before a deploy

Run the fixed adapter against candidate and baseline product code. Product
source comes from immutable Git archives; no branch switching, installation,
production access or deploy occurs. Use a worktree with `make setup` completed.

```bash
# Read-only structure capture, once per corpus. Use a NEW output directory.
source ~/.local/bin/gcp-agent-env.sh ro-prod
backend/.venv/bin/python -I backend/testing/batch_replay/capture.py \
  --output /Volumes/Ephemeral/scratch/replay/corpus/DATE --limit 2000

# Lead's predeploy gate. Pin both SHAs; never point CORPUS at raw exports.
/Users/dazheng/workspace/omi/bin/omi-heavy run -- nice -n 19 make batch-replay \
  REF=CANDIDATE_SHA BASE=LAST_GOOD_SHA \
  CORPUS=/Volumes/Ephemeral/scratch/replay/corpus/DATE/corpus.json \
  OUTPUT=/Volumes/Ephemeral/scratch/replay/gates/DATE
```

`gate.json` contains the SHAs and corpus SHA256, new exception class/site
counts, per-unit failures and owner chain blocks. `candidate.json` and
`baseline.json` contain counts, hashed chain heads and coverage. A failure is
a new exception/site, repeated exceptions on a previously exercised unit, newly blocked units,
or unexpected synthetic boundary/incident failures. Reports/logs stay outside Git. Diagnostic
`gate.py --allow-incomplete` comparisons are explicitly **not deploy receipts**.
Known exceptions exposed behind a repaired head are reported separately as
newly reached evidence; already-blocked baseline units were never successful.

The normal gate's approved scope is **Firestore structure + synthetic
geometry**, per lead ruling `a76a1a` (2026-10-29). It always also runs the
incident fixture and boundary distributions from duration quantiles: EOF
minus/exact/plus one sample, out-of-tolerance VAD, first/last valid slices,
and slices past source/capture or with zero frames. Negative cases must be
rejected. Captured geometry gaps remain visible in `coverage_limits`, and
`coverage_scope` names this narrower acceptance. No artifact export or
decryption is allowed. `gate.py --require-captured-geometry` also fails gaps.

The corpus window is the latest 2,000 committed result records by
`committed_at`, including already projected and pending/wedged rows. Capture
reads no transcript or audio and downloads no encrypted artifacts. Each
corpus has a fresh HMAC-SHA256 salt, stored separately mode 0600; the corpus
directory is mode 0700. Identifiers have equality only inside that corpus.

## Field allowlist

Firestore reads use field projections (`capture.py` constants are the exact
allowlist):

- Results: owner key, segment/predecessor IDs, sequence and committed time for
  ordering; projection state, receipt state/conversation ID, result outcome;
  optional numeric decoded duration and speech seconds.
- Jobs: owner/conversation IDs, duration/unit kind/fresh lane, state/attempt,
  recovery state/attempt, retry presence; VAD receipt captured/speech sample
  counts; binding target/content/sibling IDs and record/native booleans;
  optional numeric decoded duration and speech seconds.
- Owners: projection watermark only. Targets and one referenced redirect target:
  discarded/deleted/status, redirect, route owner and privacy flags. No user
  document is read.

Stored values are constructed field by field: HMAC identifiers, numeric
geometry, booleans, and closed state enums. No names, emails, text, URIs,
raw error strings, exact capture times or GCS generations are persisted.
No salt, corpus or captured report belongs in Git.
Firestore cannot project subfields inside array elements, so capture never
requests `speech_spans` or `manifest.references`: nested text or paths must
not be read even transiently. Corpus geometry slots remain null and the
exact RPC field allowlist is stored with the corpus. Only the synthetic
fixture/runner supplies VAD arrays and source slice geometry.
Delete the private corpus and salt after the program, per David's `a5c4f6`
ruling. The lead owns the program-end disposal handoff.

## What runs

- Real `Projector.project_owner`/assignment walk, VAD validation,
  `projection_parts` and `build_incoming`; synthetic words/diarization carry
  no production text. Real `assign_in_transaction` runs against
  `StrictFirestore` fake targets, including `live_projection.replace_record`.
- Real `source_audio.materialize` with zero PCM and recorded reference geometry.
  Source length must be observed; it is never derived from offset+frames.
- Real `ProjectionFollowups._run`, `projection_claim` and fakeredis Lua. Each
  executor leaf uses a fresh copied Context in a thread pool, reproducing
  cross-Context claim entry/release.
- Existing `pipeline_sim` result log facade with a receipt adapter. This is
  an offline functional replay, not a transaction contention/emulator test.

Python sockets, gRPC channel construction and cloud client construction are
blocked. Bridge side effects are fake leaves; summary completion is a no-op.
The adapter rewinds assignment to the beginning of the sampled owner window,
anchoring its external predecessor and preserving internal predecessor links.
It preserves recorded states in the corpus, rather than letting an existing
ready receipt bypass the candidate's validation. Summary, notification,
enrichment, search indexing and playback network side effects are not run.
Production claims are advisory; this gate does not prove Firestore concurrency.
Recorded success/silence outcomes select the real projection branch. A terminal
empty-recovery result without its artifact proof is incomplete coverage.
Missing outcomes and unknown lanes block replay with a coverage gap; neither
is converted into a successful fresh unit.

**Coverage matters:** production VAD spans/manifests generally live in encrypted
artifacts, not queue metadata. A Firestore-only corpus can have missing shapes.
The synthetic quantiles use every captured duration's observed frequency;
duplicate selected quantile values share one boundary execution.
Those fields are counted as missing; assignment uses labelled model inputs
for such units. A normal PASS establishes the approved structure plus synthetic
scope. It does not establish correctness on captured VAD/source shapes.
Capture must never fetch transcript/audio or invent observed production spans.

## Historical incident check

`regressions.json` is a separate fully synthetic incident-shape corpus. Its
one-sample EOF VAD overrun and discarded backfill chain head reproduce the
mechanisms of #23926/#23932. A sub-second provider-word EOF overrun also runs
through the real `PipelineWorker` before projection. `worker_results` records
its validation stage/reason or persisted numeric word clocks; synthetic provider
hypotheses are refused on captured corpora. It is **not captured production data**.
Each worker fixture must declare `expected_worker_result`: the actual persisted
outcome and numeric clocks must match it exactly before projection. A different
valid clock or worker outcome blocks the synthetic gate.

```bash
/Users/dazheng/workspace/omi/bin/omi-heavy run -- nice -n 19 make batch-replay \
  REF=origin/main BASE=7bc941c \
  CORPUS=backend/testing/batch_replay/regressions.json \
  OUTPUT=/Volumes/Ephemeral/scratch/replay/historical
```

Inspect both reports to verify the baseline failures and their disappearance.
A differential PASS alone does not mean baseline failures were reproduced.
