# The batch final pass splits a mixed segment at the voice change

Contract: [batch conversation speakers runbook](../../runbooks/batch-conversation-speakers.md), section
"Whole-conversation final pass". On by default inside the existing batch speaker authority, behind
`BATCH_FINAL_PASS_SPLIT_MIXED_SEGMENTS_ENABLED` (read per call; false stops new splits).

## What was wrong

The whole-conversation final pass labels every word with a voice, but it writes labels back per stored segment:
`final_pass_batch._run` relabeled a segment only when all of its words had one voice. A segment whose words span
two voices kept its earlier label, and the pass ended `failed_unassigned_words`.

The stored segments come from each unit's own grouping, and the whole-conversation pass hears many voice changes
inside them. On the owner's gold-labeled conversations (12 conversations, 9,185 words, labeled by the owner in a
decision-mill speaker task), 172 of 432 stored segments (55 % of words) held two or more voices. In the read-only
diagnosis of the owner's 24 fresh conversations-v3 rows, 16 final passes ended `failed_unassigned_words`.

## What changed

- `utils/conversations/final_pass_split.py` plans one run per voice over a segment's assigned words. Words in a
  diarizer gap join the neighbouring run while they are at most a quarter of the segment's words. A segment with
  two to eight runs splits into pieces: the first piece keeps the segment id; later pieces take
  `uuid5('<id>:split:<k>')`. Text is cut on whole tokens of the stored text (the words must spell it, up to case
  and punctuation). Clocks move with the words: a piece starts where its first word starts, relative to the
  segment's first word, and the last piece keeps the segment's end.
- Each piece is relabeled with its own voice. Manual, corrected (`original_text`) and translated segments,
  already-split pieces, segments of more than eight runs and segments whose words do not spell their text never
  split; they abstain as before.
- Splitting runs only on a conversation's first pass, never on the identity-only retry (`final_pass_retry.run_only`):
  by then structured notes may cite the segment, and a split would narrow the citation to its first piece.
- A saved sync audio window (`audio_source`) is re-timed for each piece, so each piece keeps its audio proof.
- Each piece gets its own measured speech seconds (`speaker_word_seconds`), so totals are not counted twice.
- A segment that a segment-level manual receipt covers (an assignment or a `not_me` rejection) never splits: the
  receipt is keyed by the segment id and would only cover the first piece.
- The late identity repair (`refresh_completed_speaker_identity`) skips a conversation holding split pieces
  (`split_by_final_pass`): it regroups by the units' original labels, which every piece still carries, and would
  merge the pieces back into one voice.
- A later pass reads the pieces back, whatever the kill switch: `decode_unit_evidence` recognises the run of stored pieces that a projection
  segment became, checks that they spell its text, and moves its words onto the pieces by token position.
- The retry obligation key (`final_pass_retry.scope_key`) ignores pieces after the first, so a split never opens a
  new obligation or a second paid pass for the same units.
- The conversations-v3 planner recognises a split segment as published (`_segment_keys`, and the duplicate check
  when a retained row is rebuilt): its pieces span the original segment's timing and their joined text is the
  original line, so a replan does not re-append the unsplit line, even under a new segment id.
- The result carries `split_segments` and `split_refusals` (logged as `event=batch_final_pass_split`). Outcomes and
  metrics are unchanged.

No new model call, GPU request or read: the pass already computes every word's voice.

## Evidence

- Speaker lab, owner gold set (`owner-60d`, 12 conversations, 9,185 words), the final pass's per-word voices
  written back to the owner's stored segments under each rule, scored by `testing/pipeline_lab/speakers/score.py`:

  | rule | attribution | owner precision | owner recall | wrong-name rate |
  |---|---|---|---|---|
  | production today (stored labels) | 0.560 | 0.784 | 0.686 | 9.8 % |
  | whole segments only (before) | 0.614 | 0.843 | 0.839 | 8.1 % |
  | this change (2-8 pieces, gap share 0.25) | 0.992 | 1.000 | 0.989 | 0.05 % |
  | per-word ceiling | 0.995 | 1.000 | 0.990 | 0 % |

  The operating point came from a sweep of piece cap (3, 5, 8, unbounded), minimum run (1-3 words, 0-1 s) and gap
  share (0.25, 0.5). Absorbing short runs and capping at three pieces cost the most (0.921 attribution, 0.966 owner
  precision). The simulation places stored segments on the audio by their text; the real path is measured below.
- Real batch path, read-only (`testing.pipeline_lab.speakers diagnose --final-pass`, production's
  `final_pass_batch._run` over the owner's staged units with the speaker peer replaying cassettes, writes fenced), over the owner's 24 fresh conversations-v3 rows, switch on vs off (2026-11-27):

  | | switch off | switch on |
  |---|---|---|
  | final pass `success` | 5 | 8 |
  | `failed_unassigned_words` | 16 | 13 |
  | segments split | 0 | 141 |
  | conversations `resolved` after the pass | 6 | 9 |
  | attribution (silver, the rows' own 600 words) | 0.490 | 0.725 |
  | owner precision / wrong-name rate | 1.000 / 0 | 1.000 / 0 |

  No split was refused for text, translation or the piece cap. The 13 remaining partial passes hold segments whose
  words all fall in diarizer gaps (`split_refusals: no_voice`, a few `mostly_gap`): splitting cannot place those,
  and letting gap words follow the neighbouring voice (gap share 1.0) changed none of the 13. Silver truth favours
  community-1, so attribution here ranks the write-back, not the diarizer.
- Unit tests: split at the voice change, a later pass reading the pieces back with the same obligation key, the kill
  switch, a one-word reply as its own piece, the piece cap, manual and translated refusals, gap handling, and a
  rebuilt conversations-v3 row keeping the pieces without a duplicate. Pipeline-lab speaker scenarios pass.

## Rollout and rollback

Default on per David (2026-11-27). Watch `batch_final_pass` outcomes after deploy: `failed_unassigned_words` should
fall and `success` rise, with no growth in `failed_incomplete_coverage` (pieces not read back) or
`failed_revoked`. Rollback: `BATCH_FINAL_PASS_SPLIT_MIXED_SEGMENTS_ENABLED=false` on every processing runtime. Split
segments persist; with the switch off a later pass still reads them back and relabels each piece whole.
