# Web Admin Dashboard

- **Networking:** all fetches use `hooks/useAuthToken.ts`; never call `getIdToken()`, create auth headers, or read Firestore in the client. Server routes call `requireScope(request, scope)` from `lib/auth.ts`.
- **Revenue metrics:** subscription metrics use `lib/stripe-subscriptions.ts`; never list subscriptions by price ID.

- **Permissions:** list every API handler's scope in `lib/route-scopes.ts` (a test fails otherwise); roles live in `lib/admin-access.ts`. `owner: true` is Firestore-only; only the owner appoints deputies.
- **Team agents:** `GET /api/agent/team`, `…/audit`, `…/proposals` and `POST …/proposals` take a Google ID token (aud `ADMIN_TEAM_AGENT_AUDIENCE`, SA in `ADMIN_TEAM_AGENT_SAS`); a proposal applies only when the owner or a deputy approves it. Example: [`docs/team-access.md`](docs/team-access.md).

Fetcher, SWR, partial-failure, and subscription-scope detail: [`docs/data-contracts.md`](docs/data-contracts.md).

`/dashboard` embeds uid `omi-tv-v2` from the Business org on `monitor.omi.me`;
see `grafana/README.md` and the private provisioning workflow.
TV kiosk share links: `/dashboard/tv-links` (admin) → `/tv/view/<token>` (no login); [`docs/tv-mode.md`](docs/tv-mode.md).
