# Pusher drain flush observability (2026-11-12)

## Why

The "Live audio session kept" tile reads about 81% because 300–870 audio sockets an hour close with
`queue_wait_timeout` during fleet-wide episodes. The socket's serial drain worker falls far enough behind
that the bounded projection queue stays full for 300 s. Two things could not be measured: which step of a
flush is slow (read-back, encoded upload or playback refresh), and why playback refreshes switch from
incremental appends to full discoveries during an episode (4:1 incremental in clean hours, about 1:10 in bad
hours).

## What changed

Metrics only; no behaviour change.

- `pusher_receive_work_duration_seconds`, `pusher_receive_work_stalls_total` and
  `pusher_receive_work_stalled_handlers` gain three `stage` values that split one live projection flush:
  `drain_readback`, `drain_upload`, `drain_refresh`. `drain` keeps meaning the close drain.
- New counter `omi_pusher_audio_file_full_discovery_total{cause}`, one increment per full discovery, so its
  sum equals `omi_pusher_audio_file_projection_total{mode="full"}`. Closed causes: `disabled`, `forced`,
  `no_paths`, `no_inventory`, `listing_expired`, `point_read_failed`, `order_fallback`, `projection_error`,
  `cas_conflict`.

## Reading it

During an episode compare, per stage, `rate(..._sum) / rate(..._count)` against a clean hour, and
`sum by (cause)(increase(omi_pusher_audio_file_full_discovery_total[1h]))`. `listing_expired` dominating means
flushes arrive more than 300 s apart (the drain is slow for another reason); `cas_conflict` or `forced`
dominating means a second writer or closed-socket drains are causing the rebuilds.
