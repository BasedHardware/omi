# Shared diarizer qualification

The small truth format is a JSON object mapping arbitrary conversation keys to
lists of `{"start": 0.0, "end": 0.5, "speaker": "reference-a"}`. Times are seconds
in the submitted PCM clock. No transcript text is needed. `null`, empty, unsure,
noise and mixed labels are excluded. Turns JSON maps the same keys to exclusive
`{"start": 0.0, "end": 1.0, "speaker": "anonymous-0"}` turns.

From the repository root:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/diarization_eval/score.py \
  --truth /private/truth.json --turns /private/exclusive-turns.json
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/diarization_eval/score.py \
  --truth ~/.local/share/labels/speaker-truth-2026-10/build/truth.json \
  --decision-mill --turns /private/crop-relative-exclusive-turns.json
```

Without `--turns`, decision-mill mode scores its cached per-word `pyannote`
predictions as a baseline. That baseline alone does not qualify assignment code.
The turns command runs the same `assign_words` code as both batch consumers.
Cached whole-file predictions must be cropped/rebased by each `conv_*.json`'s
`t0` before comparison. Missing-turn words count as misses; word-to-turn
assignment chooses maximum temporal overlap, midpoint on a tie, and abstains in
gaps. Overlap activity never changes the exclusive label.

The scorer computes optimal per-conversation 1:1 permutation with Hungarian
matching, many-predicted-to-one-reference accuracy, and speaker counts. Pooled
scores sum correct words before dividing; never average conversation percentages.
It prints only aggregate counts and rates, never names, text, paths or audio.
Private truth, turns and biometric vectors stay outside Git. Synthetic tests in
`tests/unit/test_final_pass_assignment.py` guard the scorer and assignment seam
through the repository's existing backend unit selector.

Every backend/pipeline/model revision needs the same truth and word-clock set,
plus public audio capacity checks; changing the corpus or exclusions is a new
qualification, not an improvement claim. Record model revision, pipeline version,
embedding space, RTF, peak CUDA allocation/device VRAM, failures and speaker count.

Existing private pyannote caches containing overlapping `intervals` can be scored
without inference or writing a derived private fixture:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/diarization_eval/score.py \
  --truth ~/.local/share/labels/speaker-truth-2026-10/build/truth.json \
  --decision-mill --cached-activity-dir \
  /Volumes/Ephemeral/scratch/diar-nemotron-2026-10-12/phase1/predictions/pyannote_no_oracle
```

This crops/rebases existing activity and uses the deterministic longest-active-turn
exclusive fallback, then production word assignment. It qualifies that fallback;
it does not claim to reconstruct community-1's native acoustic exclusive output.
Report `scored_conversations`: all-unsure/unlabeled entries are not scored evidence.
