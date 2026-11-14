# Privacy cache certification and comparisons

Cached ALLOW is usable only after a fresh durable privacy-token read matches
the entry's opaque token, Firestore server revision (including nanoseconds),
and generation. The advisory TTL and batch process cache also expire at most
60 seconds after the live authority read started. Age never authorizes reuse.
Legacy, malformed, missing, unavailable, or mismatched certification falls
through to live authority. BLOCK decisions remain uncached.

The token writer must rotate the durable token in the same commit as every
relevant authority change (`batch_privacy_write_fence`). Token certification
cannot protect a writer that bypasses that contract. Nontransactional checks
retain the documented check/write race; transactional batch checks enroll the
token in the authorizing transaction's conflict set.

The runtime `ops_kill_switches/privacy_decision_cache` reader, poll interval,
fail-closed behavior and lever defaults are unchanged. This change does not
clear the switch or enable any lever.

## Comparison evidence

`privacy shadow decision_mismatch` keeps its existing `family`, `reason`,
`live`, and `candidate` fields and one-line-per-family-per-minute process rate
limit. It adds the fields below. `privacy_decision_comparison_total` emits the
same evidence as labels for every completed comparison, with `family` and
`result=match|mismatch`. Existing aggregate mismatch counters remain available.

| Field | Closed values / meaning |
| --- | --- |
| `candidate_source` | `ttl_hit`, `token_hit` (Redis), `session_hit`, `fresh_read`, `unknown` |
| `cache_age` | `lt_1s`, `1_10s`, `10_30s`, `30_60s`, `expired`, `unknown`; age of an examined TTL entry or reused token/session entry |
| `token_versions` | `same`, `changed`, `unavailable`, `unknown`; live versus candidate token/server-revision observations |
| `generation_versions` | Same closed relations, for the corresponding generation observations |
| `marker_changed` | `true`, `false`, `unknown`; compares common observed erasure/deletion/gate markers, including cached observations |
| `cache_certification` | `matched`, `mismatch`, `unavailable`, `miss`, `not_used`; entry versus current certification |

Raw tokens, generations, revisions, marker fingerprints, document paths and
identifiers are never emitted. Marker fingerprints remain private cache/request
metadata; a token rotation by itself does not establish a marker change.
Batch marker evidence covers the owner erasure marker; individual tombstone
checks cover their one tombstone. Metadata is bounded independently of the
number of batch source conversations.
Token/session ages use wall-clock observations for telemetry only; clock skew
produces `unknown`. TTL enforcement uses the existing monotonic cache clock and
Redis expiry. Missing legacy age/marker metadata is `unknown`.

A later fresh ALLOW after the first live BLOCK is still a `stale_allow`
comparison, but `candidate_source=fresh_read` distinguishes that race from cache
reuse. Shadow always preserves the original live result or exception. No stale
ALLOW is exempted as `stale_within_ttl`, even at an age below 60 seconds.

## Merge gate

Run `tests/unit/test_privacy_ttl_cache.py` in its own pytest process through
`omi-heavy`. Its `test_external_revoke_then_check_blocks_cached_allow_within_ttl`
cases are the merge gate: after an ALLOW is cached, a completed erasure-marker
and token/generation change must cause a live marker read and BLOCK at age one
second. The same suite covers live and token-cache controls, batch reuse,
certificate outages/invalidity, both fresh-read race directions, cache-source
labels, rate limiting and identifier exclusion. The intentionally unfenced
writer tests qualify shadow detection; they do not authorize that writer.
