# Notes-first closed episode compose

Date: 2026-11-10
Owner: refactor-lead
Contract: [listen_pusher_pipeline.mdx](../../listen_pusher_pipeline.mdx) — "Notes-first closed episode compose"

## What changed

The closed-episode composer (`backend/utils/episodes/composer.py`) can now read
each member's notes instead of every member's full transcript. The notes are the
title, overview, note sections, action items and clock times the notes call
already paid to produce. When the model needs exact detail, it calls
`get_transcript_excerpt(recording, start, end)` and gets a bounded raw excerpt
from one recording.

A member with no notes still gets its transcript, bounded like the full path.
The output schema, chapter mapping, fingerprint, lease, settle window and
failure backoff are unchanged.

## Bounds

- Per excerpt call: at most 4,000 characters and 15 minutes of one recording.
- Per compose: at most 4 excerpt calls and 12,000 excerpt characters.
- Per compose: at most 5 model turns; the last turn is sent without tools, so
  the model must answer inside the cap.
- A request for a wider range is clamped, not rejected. An unknown recording,
  an out-of-span clock, or an exhausted budget returns a short error string and
  spends no characters.

## Flag and ramp

`EPISODE_COMPOSER_NOTES_FIRST` defaults off. Off, blank, `false`, `0`, `no` or an
unknown value restores today's full-transcript prompt. `EPISODE_COMPOSER_NOTES_FIRST_PERCENT`
(default `0`) is the salted uid cohort; `100` admits every owner. The flag is
the kill switch and the percent is the ramp lever.

Ramp plan (also in the feature-flag registry):

1. 0% — default off, today's behavior.
2. David-only uid digest — run the read-only side-by-side on David's own
   episodes and review the text diff before any cohort.
3. 5% — watch `omi_episode_compose_total{outcome=error|conflict}`,
   composed-per-close, `omi_episode_compose_input_tokens_total{mode}` and
   `omi_episode_compose_tool_calls{mode}`.
4. 25% — same clean metric, plus a spot check of composed pages.
5. 100% — final cohort.

The clean metric is: error and conflict outcomes do not regress against the
full-transcript cohort, composed-per-close does not fall, input tokens per
compose fall, and the tool-call rate stays inside the per-compose cap.
refactor-lead expands each step; the review date is 2026-12-10.

## Measurement

- `omi_episode_compose_input_tokens_total{mode="full"|"notes_first"}` — input
  tokens per compose, before and after.
- `omi_episode_compose_tool_calls{mode}` — excerpt calls per compose.
- Episode `usage.composer_tool_calls` — per-episode total, alongside the
  existing `composer_input_tokens` and `composer_output_tokens`.

Both metrics have bounded labels and never carry a uid.

## Side-by-side

`backend/scripts/episode_composer_notes_first_diff.py` composes an owner's recent
closed episodes both ways and writes a private text diff (mode 0600, default
`~/.omi-private/`). It is read-only: it never calls `compose`, never writes to
Firestore and never schedules work. It does spend two model calls per episode.
Run it only on an account whose owner approved the read. David approved his own
account for this review; do not run it on any other account.

## Rollback

Set `EPISODE_COMPOSER_NOTES_FIRST=off` (or the percent to `0`). The next paid
compose uses the full-transcript prompt. No data migration, no composer-version
bump and no recompose wave.
