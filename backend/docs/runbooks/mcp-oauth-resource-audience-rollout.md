# MCP OAuth resource-audience rollout

The canonical MCP endpoint is `https://api.omi.me/v1/mcp`; `/v1/mcp/sse` is a
permanent compatibility alias. The two paths mint and accept two resource
audiences that are canonical-form equivalent server-side, but they are NOT
equivalent for older deployed backends.

## Audience semantics

| Token request `resource` | Stored audience |
| --- | --- |
| omitted | `https://api.omi.me/v1/mcp/sse` (legacy) |
| `https://api.omi.me/v1/mcp/sse` | legacy |
| `https://api.omi.me/v1/mcp` | canonical |

Validation on both endpoint paths accepts both audiences
(`mcp_resource_urls_match` compares canonical forms), and protected-resource
metadata is per-path: the well-known document under
`/.well-known/oauth-protected-resource/v1/mcp` describes the canonical
resource, the `/v1/mcp/sse` document — and the unqualified root document, for
now — describes the legacy resource.

## Rollout constraint

**Clients must not switch their OAuth `resource` indicator to
`https://api.omi.me/v1/mcp` until the production backend carrying the
audience-equivalence change is deployed.** A production backend from before
this change exact-matches the stored audience against `…/v1/mcp/sse`; a token
minted with the canonical audience would be rejected there. The
protected-resource metadata clients should follow is the one their endpoint's
`WWW-Authenticate` challenge advertises — it is path-correct.

**Omi Beta uses the production authorization server** (`MCP_AUTHORIZATION_SERVER_URL`
`https://api.omi.me`) and its production grants. Beta therefore inherits the
same constraint: a beta client must keep requesting the legacy audience until
production carries this change, even though beta serves MCP data from dev.

## Rollback semantics

Tokens minted while this change is live stay valid after a rollback:

- Omitted/explicit-legacy grants store the legacy audience — exactly what the
  old backend expects.
- Explicit-canonical grants store the canonical audience and would fail on a
  rolled-back backend. That is acceptable and intentional: no client may
  request the canonical audience before this deploy (above), so the only
  canonical-audience tokens in existence were minted by clients that opted in
  after the new metadata shipped.

When flipping clients to the canonical resource later, first confirm the
serving backend image includes the audience-equivalence validator
(`mcp_resource_urls_match` in `database/mcp_oauth.py`), then update the
client's `resource` parameter; existing refresh-token families keep working
because token refresh keeps the stored audience when `resource` is omitted.

## Access-token cache and revocation TTLs

Validated access tokens are cached in Redis (`database/mcp_token_cache.py`)
under `mcp:oauth:at:{sha256(access_token)}` with a TTL of
`min(60s, access-token expiry remaining)` — a hit performs zero Firestore work
(no token read, no memory grant, no `last_used_at` write) but still
revalidates shape, expiry, scopes, audience equivalence, and the revocation
marker. Cached payloads (and cached CIMD documents under `mcp:cimd:*`) carry
an HMAC-SHA256 integrity tag over canonical JSON
(`database/mcp_cache_integrity.py`): the signing key is HKDF-SHA256-derived
from `ENCRYPTION_SECRET` with `info="mcp-cache-v1"`, and every envelope binds
a type tag (`at` for token identities, `cimd` for client metadata), so a
forged, tampered, or cross-type-reused Redis value is dropped and validation
falls through to Firestore; a missing signing secret fails closed on the
OAuth path and disables CIMD caching entirely.

Revocation (`revoke_grant`, `revoke_user_grant`,
`delete_user_oauth_credentials`, and the refresh-token replay path) writes the
marker `mcp:oauth:revoked:{sha256(grant_id)}` with `EX` = the access-token TTL
**before** the Firestore revoke, and the marker write is mandatory: when
Redis cannot take it the revoke raises `McpTokenStoreUnavailable` — no 204 /
no refreshed token is reported while a stale cached token could outlive the
outage. Once the marker is written it blocks every cached entry for the grant
even if a later purge step fails. The marker ordering plus a re-check after
the cache fill protects the in-flight race: a validation that loaded the
grant before revocation re-checks the marker before crediting the request.
The grant token index `mcp:oauth:grant_tokens:{sha256(grant_id)}` (expiry =
access-token TTL) tracks each cached token hash so revoke also deletes the
cached entries directly.

`last_used_at` grant writes happen only on validated misses, throttled by
`mcp:oauth:last_used:{token_hash}` claimed with `SET NX EX 600` — at most one
Firestore write per token per 600 seconds, and never on cache hits or invalid
tokens.

During a Redis outage, token *validation* degrades instead of failing: the
cache read, revocation marker, last-used throttle, and the `last_used_at`
write itself are all skipped — an unthrottled write per validated request
would add ~150k+ Firestore writes/day at steady traffic — and the token and
grant are verified against Firestore, the authoritative store, with a
warning log (no secret values). Marker-first revoke ordering shrinks the
stale-accept window but does not eliminate it: a marker written just before
an in-flight Firestore revoke commit is unreadable while Redis is down, so
that one grant can keep validating for the Firestore write's commit latency.
The window is narrow — marker and Firestore writes are adjacent — and it
closes as soon as the revoke commit lands. If *Firestore* is the failing
store, validation maps to `503 + Retry-After` — never a 401 that would make
a client discard a valid token.

Revocation is unaffected by the degrade: the marker write stays mandatory,
so `revoke_grant` (the REST grant-revoke route and the `/token` refresh
replay path) still raises `McpTokenStoreUnavailable` → `503` /
`temporarily_unavailable` when Redis cannot take the marker — no 204 / no
refreshed token is reported while a stale cached token could outlive the
outage. The account-deletion wipe retries safely: the failed revoke leaves
the grant unrevoked, so the retried wipe re-writes the marker and completes.
The refresh-replay branch likewise records only `replay_detected_at` intent
on the refresh doc inside its transaction — grant and token revocation
always flow through `revoke_grant` after the marker, so every retry of a
used refresh token re-enters the revoke path instead of finding a
half-revoked state. A marker `SET` that returns falsy without raising is
treated as an unwritten marker and fails the same way.

## CIMD fetch hardening

URL-form `client_id` values (Client ID Metadata Documents) are supplied by
unauthenticated callers and fetched from arbitrary hosts. The fetch path
(`database/mcp_client_metadata.py`) therefore runs on dedicated bounded
pools — `cimd_executor` (4 workers, small queue, `utils/executors.py`) for
the whole lookup dispatched by the OAuth layer, and a module-local
4-worker/8-queue pool inside the module for `getaddrinfo` — so a hostile
`client_id` flood can never park `db_executor` or the event-loop threadpool
on outbound I/O.
Saturation returns a fast `503 temporarily_unavailable` on `/authorize`
(GET and POST) and `/token`, and a per-host rate limit
(`mcp:oauth_url_client`, keyed by the normalized `client_id` metadata host —
the connection peer is the load balancer and forwarded headers are never
trusted) throttles the unauthenticated lookups before they reach the pool.
A generous global bucket (`mcp:oauth_url_client_global`, checked first)
backstops it when many distinct hosts attack at once; malformed URL-form
ids share a single `invalid` bucket.

Every fetch shares one hard monotonic 3-second deadline across DNS, connect,
the TLS handshake, and the iterative ~1 KiB body reads (each `recv` is
re-timed to the remaining budget, so a slow-drip peer cannot hold a
worker). URLs carrying a query string or fragment are rejected outright —
cache-busting cannot mint distinct fetch identities — and failures are
negative-cached for 60 seconds keyed by the canonical URL. DNS answers are
all validated: any private, loopback, link-local, multicast, unspecified,
reserved, NAT64 (`64:ff9b::/96`, `64:ff9b:1::/48`), IPv4-compatible
(`::/96`), 6to4 (`2002::/16`), Teredo, or unsafe IPv4-mapped/embedded
result rejects the whole host; validated addresses are tried IPv4-first
inside the deadline. TLS is pinned to the validated address with hostname
verification on the original host; redirects are never followed. Every
self-published `client_name` is displayed suffixed with the verified ASCII
host — an exact-match brand list cannot catch homoglyph spoofs like
Cyrillic "Сlaude".
