# Episode owner context and scaled detail

New paid composes append owner name, output language, timezone, the existing
cached AI profile, up to five active goals and up to twenty people already
bound to the episode's speech. The prompt treats all background as data, not
instructions or proof that events occurred, people attended, or a speaker is
identified. The raw transcript remains authoritative.

Relevant memories come from the chat prompt's existing processed/default-visible
intake (at most 1000 candidates, existing 30-second cache). Local inverse-document
frequency overlap ranks episode title/overview and raw-speech terms against facts.
Only matching facts qualify; locked, rejected and invalidated facts stay out.
At most twenty are rendered, at most 700 tokens each, and the entire memory
block is capped at 3500 o200k tokens. The owner block is capped at 1000 tokens.
If the tokenizer is unavailable, UTF-8 byte bounds are more conservative.
No extra embedding or model request is made. Each context source fails open
independently. This bounded lexical selector can miss semantic paraphrases;
retrieval quality remains a private replay result, not a guaranteed recall rate.

Detail scales with speech and recorded duration. At 30000 words over four hours,
the target is 2550-3450 words and at most fifteen chapters; the configured hard
ceiling is twenty chapters. Sparse speech stays short even over long durations.
Long single-recording episodes use the full composer; short single-recording
notes still reuse the existing paid notes. Points/details retain the existing
six/four bounds and 400-character text bound. Config lives in `config/episodes.py`.

No `COMPOSER_VERSION` bump and no context, language, owner, budget or switch
input in `fingerprint`. What makes an old episode recompose after rollout?
Nothing. Existing speech/name/membership changes, explicit regeneration and
existing notes-drift recovery retain their previous meaning.

Rollback independently with `EPISODE_COMPOSER_CONTEXT_ENABLED=false` and
`EPISODE_COMPOSER_DETAIL_ENABLED=false`. They restore the old prompt inputs,
eight-chapter ceiling and single-member reuse. Already stored richer notes stay
readable; rollout never bulk regenerates them.

## Client source check

`origin/main` decodes arbitrary lists in `app/lib/backend/schema/episode.dart`,
iterates every chapter/point/detail in `episode_sections.dart`, and places the
body in the scrolling `episode_page.dart` ListView, with wrapping Expanded Text.
There is no list slice, maxLines or ellipsis in that body. The iOS build tag
`v1.0.577+1520-ios-cm` has the same unbounded renderer. The Android tag
`v1.0.577+1516-android-cm` predates the composed episode page entirely; it cannot
show composed chapters. Lowering the new chapter ceiling to eight would not
make that old build show them. Actual store distribution and device layout
were not verified; the released-client catalog has no admitted release fixtures.
The backend's existing 48-moment storage limit exceeds the new twenty ceiling.

## Cost model

At the supplied 11-10 baseline of 27000 paid composes/day, about 21000 input
tokens/compose and about $64/day composer input, a full 4500-token background
adds at most 21.4% input volume: about $0.000508/compose or $13.71/day at that
observed blended input rate, before cache effects. The guidance itself also
adds a small prompt suffix. Additional output must be measured by replay;
every extra 1000 output tokens/compose costs $0.0006 or $16.20/day on the
repository's `openai.gpt-6-luna.2026-09-22` planning card (not a vendor invoice).
The new long-single-recording path can add paid call volume; its fleet frequency
has not been measured, so a fleet total including that path remains unverified.

Cold context intake can read up to 1000 memory records per paid compose,
plus bounded people/profile/goals reads; the shared thirty-second cache reduces
repeated reads but does not promise a hit per episode. At 27000 cold composes
that is an upper bound of 27 million candidate records/day, not a measurement
of actual Firestore billable reads. No fleet scan is introduced.

Context-on prompts also require grounded ledes and follow-ups: no whole-day or
day-ended narrative beyond captured clocks, no speaker attribution guessed from
background, and no tentative suggestion promoted into an assigned task.
