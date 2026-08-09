# Admin TV mode

## Surfaces

| Path | Auth | Purpose |
| --- | --- | --- |
| `/dashboard` (TV wall links panel) | Firebase admin | Create / list / revoke share links |
| `/tv/view/<token>` | Capability token in path | Kiosk wall view; no Google login |
| `GET /api/tv/snapshot` | Admin bearer **or** TV token | Aggregate metrics only |
| `GET/POST /api/omi/tv-links` | Firebase admin | Manage share links |
| `DELETE /api/omi/tv-links/[id]` | Firebase admin | Revoke a share link |

Standalone `/dashboard/tv` and `/dashboard/tv-links` routes were removed — kiosk is link-only; management lives on the main dashboard.

## Share links

- Firestore collection: `admin_tv_links`
- Store **SHA-256 hash** of the token only; show raw token once on create
- Default expiry 90 days (editable; empty = never)
- `ttlDays` must be a positive integer, `null` for never, or omitted for default — invalid values are rejected
- `includeRevenue` defaults true; revoke is immediate
- Auth helper: `verifyAdminOrTvSnapshot` in `lib/auth.ts` — never wire TV tokens into mutating routes
- Opaque TV tokens skip Firebase JWT verification so kiosk polls do not spam auth error logs

## Snapshot contents

- Stripe ARR/MRR via `computeRevenue` (optional per link; unavailable Stripe is marked partial)
- PostHog activity (DAU/WAU by platform via `$os_name`/`$os`, conversation/chat/memory boards) via `posthogResults`
- Days-to-1M from PostHog `persons` + 7-calendar-day avg new persons/day (zero-filled missing days)
- Chat metrics use `floating_bar_query_sent` (sent queries only, not panel opens)
- No Prometheus; no M1 retention; no PII
- If every enabled source fails, the snapshot endpoint errors (502) instead of caching an empty board

## Client conventions

- On poll error or revoke, clear the snapshot so tiles show N/A (never stale metrics beside an error)
- Clock ticks live in an isolated component so the board does not re-render every second
