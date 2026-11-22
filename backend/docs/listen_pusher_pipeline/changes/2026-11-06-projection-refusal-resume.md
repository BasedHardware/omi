# Resume stale projection privacy refusals

A stale job privacy hint no longer keeps a projection head blocked after the transactional hold reports
`privacy refusal no longer applies`. A stored refusal uses the existing fenced replay; otherwise the
wrapped operation retries once. Hinted reads reload the durable projection policy before assignment,
so settlement-only defaults cannot authorize content. Applicable privacy refusals, deletion and
tombstone handling retain their existing fences and dispositions.

`PROJECTION_PRIVACY_REFUSAL_RESUME` defaults on; only `off` restores the prior exception behavior.
The serving GMP profile retains attempted/succeeded replay, fall-through and still-refused counters;
these counters carry no owner or conversation labels. See the [flag registry](../../feature-flag-registry.md).
