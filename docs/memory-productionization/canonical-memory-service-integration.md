# Canonical PostgreSQL memory service integration

## Scope

`createPostgresFirebaseAuthorizedMemoryServiceApp` is the route composition for
the first authoritative product read. It joins:

- the existing strict Hono service shell;
- the existing `GET /v1/memories` collection route and transitional alias;
- the route-free PostgreSQL/Firebase authorized graph reader; and
- the caller-injected existing `/mcp` handler.

It does not bind a socket, read environment variables, choose credentials,
activate a cohort, or create another memory endpoint.

## Public behavior retained

Authentication still precedes query validation. The route verifies only
Firebase identity for an invalid query, so an invalid credential plus an
invalid query remains the existing fixed `401`; it does not load a graph or
turn validation into an authentication oracle. A valid query performs the full
authorization and final-fenced read.

The response classes remain:

| Internal result | Existing route result |
| --- | --- |
| malformed/failed identity | fixed `401 unauthorized` |
| authorization or stale epoch | fixed `403 forbidden` |
| branded invalid cursor | fixed `400 bad_request` |
| unavailable, invalidated, malformed adapter result | fixed `500 internal_server_error` |
| ratified canonical page | `200` with the unchanged page bytes |

No internal authority reason, identifier, provider error, graph coordinate, or
content is interpolated into a failure.

## Security and authority

The route accepts a sealed `MemoryRouteReadPort`; it never imports PostgreSQL or
Firebase. The driver adapter captures exact methods at construction, validates
plain-data outcomes, and re-parses successful bytes with the ratified contract
parser before counting or emitting them.

The PostgreSQL runtime still performs its repeated authorization/coherence
loads around rendering and before emission. Restored-generation release and
per-account retained tombstone checks remain inside the same database-backed
authorization path. The served counter advances only after valid canonical
bytes exist.

## MCP boundary

The REST route and `/mcp` are mounted on one Hono application. This prevents a
second service or native memory API. The MCP handler remains injected because
MCP API-key authentication, persisted grant lookup, rate limiting, and final
reauthorization are distinct from Firebase app identity. This unit does not
pretend Firebase is an MCP credential and does not claim the production MCP
adapter is finished.

## Qualification

The pinned PostgreSQL 18.4 real test commits an authoritative, cited graph,
then reads it through the actual Hono route. The emitted body is accepted by the
shared ratified parser, contains non-empty cited items, and carries an honest
completeness envelope. The same test proves invalid cursor refusal and then
installs a retained restore tombstone; the next request returns the fixed 403
without incrementing the served count. Bun 1.3.14 and Node 24.19.0 retain the
normalized PostgreSQL client parity result.
