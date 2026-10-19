# Web Admin Dashboard

- **Networking:** all fetches use `hooks/useAuthToken.ts`; never call `getIdToken()`, create auth headers, or read Firestore in the client. Server routes call `verifyAdmin(request)` from `lib/auth.ts`.
- **Revenue metrics:** subscription metrics use `lib/stripe-subscriptions.ts`; never list subscriptions by price ID.

- **Admin removal:** `adminData/{uid}.owner === true` marks the workspace owner; only the owner can `DELETE /api/omi/team-members` (any role, never themselves). Set the flag in Firestore, never through the UI.

Fetcher, SWR, partial-failure, and subscription-scope detail: [`docs/data-contracts.md`](docs/data-contracts.md).

`/dashboard` embeds uid `omi-tv-v2` from the Business org on `monitor.omi.me`;
see `grafana/README.md` and the private provisioning workflow.
TV kiosk share links: `/dashboard/tv-links` (admin) → `/tv/view/<token>` (no login); [`docs/tv-mode.md`](docs/tv-mode.md).
