# Production Settings reads

The deployed service mounts `GET /v1/settings` through the same admission,
readiness and drain boundary as the other REST routes. Absent credentials return
the signed-out envelope `{identity:null,entitlement:null}`. Present invalid
credentials are 401. A verified Firebase identity without an owner-backed profile
and entitlement producer is 503 `{error:"service_unavailable"}` with
`retry-after: 60`. Token claims are never projected as display names, emails, or
plans. PostgreSQL account/grant rows are not a Settings producer.

Mutations stay unmounted. Unmounted writes stay 404 `{error:"not_found"}`. Do not
invent identity, billing, or usage to satisfy the page.

Verification uses `bun run check:deployed` for signed-out, unauthorized, verified
unavailable, grammar, pairing and the production import closure. These tests use
isolated synthetic identities; they do not activate a deployed user or prove a
billing producer.
