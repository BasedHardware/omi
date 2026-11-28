# A partial batch final pass keeps the resolver's voices

Contract: [batch conversation speakers runbook](../../runbooks/batch-conversation-speakers.md), section
"Whole-conversation final pass". On by default inside the existing batch speaker authority, behind
`BATCH_FINAL_PASS_KEEP_RESOLVED_ON_PARTIAL_ENABLED` (read per call; false restores the previous behaviour).

## What was wrong

The mobile app shows plain "Speaker" for every unnamed voice when `speaker_resolution.status` is `unavailable`
(`app/lib/backend/schema/conversation.dart`, `transcript_tab.dart`), and "Speaker 1", "Speaker 2" when it is
`resolved`. After the v3 batch speakers change (2026-11-26), the resolver (`_resolve_original_batch`) groups the
voices of a v3 row and marks it `resolved`; the whole-conversation final pass runs last. When it cannot update
every segment (a segment mixing two voices, diarizer-gap words, manual or other-lane segments), it applied the rest
under new speaker ids (the conversation's highest id plus one, and so on) and stored `unavailable`.

- Read-only diagnosis of the consenting owner's 24 fresh v3 rows (2026-11-26): the resolver resolved 19; the final
  pass ended partial (`failed_unassigned_words`, labels still applied) on 16 and set them `unavailable`; about 7 of
  24 ended `resolved`.
- The new ids sat beside the resolver's ids on the skipped segments, so one person could appear under two numbers.
  The `unavailable` status then hid every number.

## What changed

On a partial pass over a conversation that was `resolved` before it, `final_pass_batch._run` maps each final-pass
voice onto the resolver voice that holds most of its assigned words (more than half). The map must be one to one
in both directions:

- **Split.** Two final voices on one resolver voice keep today's behaviour.
- **Merge.** A resolver voice whose words mostly belong to a final voice mapped elsewhere keeps today's behaviour.

Updated segments then reuse the resolver's id. The conversation stays `resolved` when, after application, each
speaker id holds a single scope and identity across the automatic segments (`_consistent_voices`; the app numbers
voices by `speaker_id` alone). Otherwise the pass applies today's new ids and `unavailable`.

Manual segments are never updated. Their words count toward the resolver voice they belong to, and their labels
are excluded from the identity check. Identity rules are unchanged: a voice whose naming is `unknown` keeps existing
labels. If that leaves one id with two names, the identity check refuses the mapping.

Outcomes and metrics are unchanged; the result carries `partial_resolution` (`kept`, `ambiguous`, `split`,
`merge`, `inconsistent`, `not_resolved` or `disabled`), logged as `event=batch_final_pass_partial_resolution`.
Recurring learning is still suppressed on any partial pass.

## Evidence

- Lab scenario `speaker_partial_final_pass_keeps_voices`: three public LibriSpeech voices (owner, enrolled person,
  stranger) with short turns. The final pass ends `failed_unassigned_words` on two one-word diarizer-gap segments.
  Same-ref compare `scenario compare --arm off --arm on --metric speakers` (switch false/true): `resolution`
  `unavailable` -> `resolved`; attribution 0.9706, owner precision and recall 1.0, named accuracy 0.9524 and wrong-name
  rate 0 in both arms; voices 4 in both (truth 3). The fourth voice is the two one-word fragments that neither pass
  placed; they keep the resolver's own unit-scope labels.
- Local recordings for this change: three public LibriSpeech conversations ended partial. These were the committed
  three-speaker one and two probes generated with tighter turns, which were not committed. Across them the pass
  skipped 5 segments, each a single word in a diarizer gap; none mixed two voices. The lab therefore exercises the
  status fix but not a visible two-number split. The split is covered by unit tests and should be measured on owner
  data (below).
- Unit tests in `test_batch_final_pass.py`: mapping, split and merge fallbacks, majority rule, identity
  disagreement, manual segments, kill switch off and an unresolved prior. Seven single-decision mutations each fail
  a test.

## Not shipped: the 80 % dominant-voice option

The option was to assign a segment whose words are at least 80 % one voice (the rest another voice or diarizer
gaps) to that voice instead of abstaining. It was measured, not shipped. In the lab conversations above, 0 of 5
skipped segments qualify: each is a single gap word. The lab therefore shows no resolved-coverage gain, and the
precision cost cannot be measured there. Revisit it after the owner-data measurement shows how often skipped segments
are dominated mixes.

## Rollout and gates

Default on, served with the release; any failed gate is a rollback by switch (false on every processing runtime;
published labels persist).

1. Staging: one synthetic v3 capture through Finish; `batch_final_pass_partial_resolution` log outcomes appear on
   partial passes.
2. The consenting owner's account: `python -m testing.pipeline_lab.speakers diagnose ... --corpus owner-fresh
   --final-pass --label partial`, and the bench arms. The share of fresh v3 rows ending `resolved` should rise and the
   distinct-voice count should fall toward truth. Owner precision must stay 1.000 and the wrong-name rate 0.
3. Fleet: `omi_conversation_speaker_resolution_voices{stage="resolved"}` and the final-pass outcome counts over equal
   windows. A rise in the `Speaker Identity Confirmed` corrected share is a rollback.
