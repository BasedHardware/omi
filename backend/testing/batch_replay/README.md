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
a new exception/site, an exception reaching a new unit, a new chain head
block, or incomplete input coverage. Reports/logs stay outside Git. Diagnostic
`gate.py --allow-incomplete` comparisons are explicitly **not deploy receipts**.

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
  optional numeric decoded duration, speech seconds, VAD span arrays and
  manifest reference geometry.
- Jobs: owner/conversation IDs, duration/unit kind/fresh lane, state/attempt,
  recovery state/attempt, retry presence; VAD receipt captured/speech sample
  counts; binding target/content/sibling IDs and record/native booleans;
  optional numeric decoded duration, speech seconds, VAD/reference geometry.
- Owners: projection watermark only. Targets: discarded/deleted/status and
  redirect only. No user document is read.

Stored values are constructed field by field: HMAC identifiers, numeric
geometry, booleans, and closed state enums. No names, emails, text, URIs,
raw error strings, exact capture times or GCS generations are persisted.
No salt, corpus or captured report belongs in Git.

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

**Coverage matters:** production VAD spans/manifests generally live in encrypted
artifacts, not queue metadata. A Firestore-only corpus can have missing shapes.
Those fields are counted as missing; only assignment is modelled for such
units. A passing comparison with missing geometry cannot authorize a deploy.
Capture must never fetch transcript/audio or invent missing production spans.

## Historical incident check

`regressions.json` is a separate fully synthetic incident-shape corpus. Its
one-sample EOF VAD overrun and discarded backfill chain head reproduce the
mechanisms of #23926/#23932. It is **not captured production data**.

```bash
/Users/dazheng/workspace/omi/bin/omi-heavy run -- nice -n 19 make batch-replay \
  REF=origin/main BASE=7bc941c \
  CORPUS=backend/testing/batch_replay/regressions.json \
  OUTPUT=/Volumes/Ephemeral/scratch/replay/historical
```

Inspect both reports to verify the baseline failures and their disappearance.
A differential PASS alone does not mean baseline failures were reproduced.
