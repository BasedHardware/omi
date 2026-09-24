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
an HMAC-SHA256 integrity tag over canonical JSON keyed by `ENCRYPTION_SECRET`
(`database/mcp_cache_integrity.py`), so a forged or tampered Redis value is
dropped and validation falls through to Firestore; a missing signing secret
fails closed on the OAuth path and disables CIMD caching entirely.

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

During a Redis outage every token-validation cache/marker/throttle operation
fails closed with a typed unavailable error mapped to `503 + Retry-After` —
never a 401 that would make a client discard a valid token, and never a silent
uncached authorization. The same 503 mapping applies to the REST grant-revoke
route and the `/token` refresh path (`temporarily_unavailable`), and the
account-deletion wipe retries safely: the failed revoke leaves the grant
unrevoked, so the retried wipe re-writes the marker and completes. The
refresh-replay branch likewise records only `replay_detected_at` intent on the
refresh doc inside its transaction — grant and token revocation always flow
through `revoke_grant` after the marker, so every retry of a used refresh
token re-enters the revoke path instead of finding a half-revoked state. A
marker `SET` that returns falsy without raising is treated as an unwritten
marker and fails the same way.
