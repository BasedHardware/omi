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
