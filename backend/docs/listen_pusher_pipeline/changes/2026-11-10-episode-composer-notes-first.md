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
- Per compose: at most 5 model turns for notes/excerpt reasoning; the last turn is sent without tools, so
  the model must answer inside the cap.
- A request for a wider range is clamped, not rejected. An unknown recording,
  an out-of-span clock, or an exhausted budget returns a short error string and
  spends no characters.

## Flag and ramp

`EPISODE_COMPOSER_NOTES_FIRST` defaults off. Off, blank, `false`, `0`, `no` or an
unknown value restores today's full-transcript prompt. This is the independent L9
switch. It stays OFF until David records a side-by-side verdict. The read-only
operator comparison does not require turning on serving traffic.

After that verdict, refactor-lead may enable L9 through normal gates, with David's
approval. Watch error/conflict outcomes, composed-per-close, input tokens per
compose, and excerpt-tool bounds. Review by 2026-12-10; absent a verdict, remain OFF.

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

Set `EPISODE_COMPOSER_NOTES_FIRST=off`. The next paid
compose uses the full-transcript prompt. No data migration, no composer-version
bump and no recompose wave.

## Split-review dispositions

L9 follows L8a #25073 and L8b #25065. It remains default OFF until David's side-by-side verdict. Compare cumulative billed input and output, logical turns, retries and failures per completed compose on identical episodes, not excerpt characters alone. A tool loop may resend notes and exceed full-mode input; no savings claim or automatic ramp is made.

The lease covers five reasoning turns plus one repair, with two bounded provider attempts per turn, retry headroom and a write margin. Full mode retains the L8b claim duration while L9 is off. Every new turn checks remaining deadline and claim ownership; stale release/final writes are fenced. A two-replica regression crosses 240 seconds through tool turns and repair. Mid-loop failure counts every paid turn toward backoff (correctness P2-1).

Action-items-only and title-only members retain their transcript; readable overview, sections or gist qualify as notes (correctness P2-3 / tests review). Unknown tools and excess parallel excerpt calls have direct regressions. Tiny budgets return a complete exhausted-budget error rather than a partial marker (correctness P2-10). L8b records reported input/output on every reply, including terminal failures; hidden provider retries remain an authoritative usage-ledger follow-up. No production inventory/dashboard is fabricated before these families serve.
