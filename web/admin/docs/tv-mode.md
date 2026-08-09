# Admin TV mode

## Surfaces

| Path | Auth | Purpose |
| --- | --- | --- |
| `/tv/view/<token>` | Firebase admin (full-bleed layout) | Logged-in wall view |
| `/tv/view/<token>-links` | Firebase admin | Create / list / revoke share links |
| `/tv/view/<token>` | Capability token in path | Kiosk; no Google login |
| `GET /api/tv/snapshot` | Admin bearer **or** TV token | Aggregate metrics only |

## Share links

- Firestore collection: `admin_tv_links`
- Store **SHA-256 hash** of the token only; show raw token once on create
- Default expiry 90 days (editable; empty = never)
- `includeRevenue` defaults true; revoke is immediate
- Auth helper: `verifyAdminOrTvSnapshot` in `lib/auth.ts` — never wire TV tokens into mutating routes

## Snapshot contents

- Stripe ARR/MRR via `computeRevenue` (optional per link)
- PostHog activity (DAU/WAU, desktop/mobile, chat/memory users) via `posthogResults`
- Days-to-1M from PostHog `persons` + 7d avg new persons/day
- Floating bar 30d usage
- No Prometheus; no M1 retention; no PII
