# Episode composer: late episodes compose on first open

Default-on `EPISODE_LATE_COMPOSE` stops paying for a whole-episode compose at
finalize when the capture is older than `EPISODE_LATE_COMPOSE_AFTER_HOURS`
(default 48). Repair waves deliver members hours apart, so the finalize compose
ran once per arrival for an episode nobody was looking at.

A late episode is stamped `compose_deferred_at` and keeps the first retained
member's own summary title, so the Home row still reads as a real title. The
compose runs when the episode page is first opened (`GET /v1/episodes/{id}`,
`composer.schedule_opened`), at most once per read-throttle window.

## Exits

- **Page open** composes immediately, bypassing the deferral gate.
- **Read-side safety net** composes a deferred episode after
  `EPISODE_LATE_COMPOSE_GRACE_HOURS` (default 24), so a client that never opens
  the page cannot leave notes unwritten. A repair wave's arrivals are hours
  apart, so a day still collapses a wave into one compose.
- **`EPISODE_LATE_COMPOSE` off** restores today's behavior: every closed episode
  composes as soon as its members finish, however old the capture is.

The deferral is one-shot: a successful compose clears `compose_deferred_at`, so
a later arrival defers again on its own. A composed episode keeps its composed
title when it re-defers.

A failed deferral stamp falls through to today's finalize compose, so a write
fault never strands an episode's notes. `omi_episode_compose_trigger_skipped_total`
gains the bounded reason `late_deferred`.

## Client note

The released app opens the episode page from the Home list and does not call
`GET /v1/episodes/{id}`. Until a client calls it on page open, the 24-hour
read-side grace is the only exit for a deferred episode. The page already
renders the pending state (live bullets) without a spinner.

Tests: `backend/tests/unit/test_episode_composer.py` covers the finalize skip,
the first-open compose, the normal-episode path, the switch-off rollback, the
grace window and the configurable threshold; `test_episodes_router.py` covers
the page-open trigger.
