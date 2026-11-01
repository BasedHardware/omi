# Empty capture recovery and reversible hiding

`scripts/capture_empty_recovery.py` is an operator tool for conversations linked
to dead-lettered finalization jobs in an explicit half-open UTC creation window.
It does not change finalization jobs, batch ownership, rollout flags or audio.
Deploying a backend revision does not run it. Run it only under a separately
authorized operator window, after the batch ramp has finished.

Use the worktree's locked Python environment. Inject `ENCRYPTION_SECRET` securely
before starting; never put its value in argv or a file. `census`, `reprocess` and
`hide` default to read-only metadata counts. `measure` also reads assigned audio
and runs local Silero VAD. Reports contain aggregate counts only, with no row
identities, titles, transcript text, object paths or exception bodies.

```bash
backend/.venv/bin/python backend/scripts/capture_empty_recovery.py census \
  --after 2026-10-29T12:00:00Z --before 2026-10-31T12:35:00Z
backend/.venv/bin/python backend/scripts/capture_empty_recovery.py measure \
  --after 2026-10-29T12:00:00Z --before 2026-10-31T12:35:00Z \
  --sample-size 400 --seed 20261031
```

The window uses **job creation time**, not recording time. Queries are paged,
field-masked, limited by `--max-jobs` (default 20,000), and paced by
`--pace-seconds` (default 0.5). A scan over its cap refuses; it never presents a
partial scan as a complete census. Document reads and audio object operations
are reported separately. The sample is uniform without replacement over visible
server-recovery rows whose transcript actually decodes empty and whose summed
audio metadata duration is at most 60 seconds. Selection for measurement is
independent of the stricter mutation fences. Unreadable audio remains a separate
unknown class, never zero speech. Wilson 95% intervals use the entire sample as
denominator, including unknowns; they describe sampling uncertainty only, not
VAD accuracy or clustering by person.

Reprocessing selects empty server-recovery rows with more than 60 seconds of
audio metadata, plus empty, untitled server-recovery/capture-end shells. Missing
or unauthenticated transcripts on titled rows abstain. Standard and enhanced
rows use the existing transcript decoder; enhanced output is encrypted using the
row's persisted protection level. User titles, notes, summaries, edits, manual
speaker assignments, kept/starred/folder choices, photos, locked rows and another
record owner are protected. Unknown structured fields abstain.

Retained audio comes only from the existing private-cloud custody bucket. Every
manifest chunk clock must still exist and the retained prefix must have no extra
unreferenced clocks or multiple objects sharing a clock. Ambiguous aliases
abstain instead of contributing an unreferenced tail. Reads pin object generations and reuse
the batch source decoder. Missing, malformed, conflicting overlap, unsupported
or oversized audio abstains. The tool never deletes, uploads or saves audio.
Reprocessing uses the existing batch CPU multilingual recovery recognizer and its
strict VAD/word validation. It fills transcript segments only; it preserves all
existing titles and summaries and does not run enrichment or notify anyone.

Apply requires all of `--apply`, `--concurrency 1`, `--max-count`, and
`--max-audio-seconds`, plus an explicit `CAPTURE_EMPTY_APPLY_AUTHORIZED` value of
`empty-capture-recovery-v1`. The tool deliberately supports one serial worker.
`--max-count` limits selected rows per invocation. Reprocess also bounds total
decoded audio before provider dispatch; the per-row decoded limit is at most
two hours. No STT is called in dry-run. A missing provider environment refuses
the attempt; inject it through the authorized runtime, not a personal login.

A transaction compares the whole-document update time, claims a row before one provider
attempt and fences the transcript fill afterward. It reuses the batch privacy
authority: account-deletion marker, existing account/protection policy, hashed
privacy generation, conversation tombstone and redirect fences. All are in the
same transaction read set as the row. Fresh checks also run before audio reads
and after VAD immediately before provider dispatch. The latter requires the
exact claimed row revision and rechecks both lock and native record ownership.
The original jobs must
explicitly declare `requires_byok=False`, remain dead-lettered and still name
this row. BYOK, custom STT and unknown payer authority abstain. The census checks
deletion markers before fetching row content. Any concurrent row change
leaves its transcript unchanged. The durable `capture_empty_recovery` marker
prevents duplicate attempts across reruns and overlapping windows. A claimed,
failed or uncertain attempt is reported as already attempted and requires
operator investigation; there is no automatic paid retry. A later window can
select newly accumulated rows without resetting earlier receipts.

An uncertain mutation receipt or a failed ledger write stops the invocation,
reports a closed unproven outcome and exits nonzero. A hide whose commit receipt
is lost is never reported as a kept row. Do not retry an ambiguous mutation
blindly; inspect its durable marker and write-ahead intent first.

Hiding sets the existing reversible list field **`discarded=True`**. It never
sets `deleted`, removes a row, or deletes audio. Only a short row measured with
**zero** detected speech is eligible; any positive speech, even one 32 ms VAD
window, stays visible. `reprocess --include-short-speech` lets a separately
authorized recovery run measure and recover those short rows too. The threshold
is conservative because VAD can miss quiet speech; zero detection is not proof
of no human speech. Metadata-only hide dry-run counts are potential candidates,
not a claim that unmeasured rows may be hidden.

Apply-hide requires `--ledger` naming a fresh file directly under
`/Volumes/Ephemeral/scratch/capturereprocess/`. The directory must be mode 0700;
the file is created exclusively at mode 0600, cannot be a symlink, and is locked
for the run. Each fsynced write-ahead intent contains only the private row
identity, previous discard flag, the operation marker and a content digest; no
audio, transcript or title. Keep it outside Git. If a commit's receipt is lost,
the write-ahead intent identifies the uncertain write for operator investigation;
automatic undo refuses without its committed revision. A truncated
or corrupt ledger refuses and must be investigated without copying its content
into a report.

Undo defaults to read-only:

```bash
backend/.venv/bin/python backend/scripts/capture_empty_recovery.py undo \
  --ledger /Volumes/Ephemeral/scratch/capturereprocess/rollback.jsonl
```

After authorization, the undo command adds `--apply --concurrency 1 --max-count
10 --max-audio-seconds 60` and the same explicit apply environment value. Undo
restores only the exact discard owned by this ledger, verifies the unchanged
content digest and original committed revision, and uses a fresh whole-row
update precondition. It refuses a
deleted, redirected, restored or edited row. Repeating undo cannot revive a
different discard. Unit tests cover actual standard/enhanced codecs, precondition
races, paid-attempt idempotence, private write-ahead hide and undo, retained Opus
decoding, and local VAD.

Hide and undo require the existing Typesense writer to be configured and enabled
before any mutation, and synchronously call its post-write convergence hook with
the current durable row. A failed hook stops with `visibility_index_unproven`;
the row mutation and ledger receipt may already be committed. After restoring
index availability, run `index --ledger <private-ledger>` (dry-run default), then
the same explicit apply/caps/environment arguments to reconcile search only.
That command checks current privacy authority and never repeats a hide or undo.
No backend deployment is required for this operator CLI.
