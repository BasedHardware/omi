# Web Admin Dashboard — Developer Guide

## Networking

All fetches go through `hooks/useAuthToken.ts`. No direct `getIdToken()`, manual auth headers, or client-side Firestore reads.

- **SWR reads**: `useAuthToken()` + `authenticatedFetcher`
- **Mutations**: `useAuthFetch()` → `fetchWithAuth(url, init)`
- **Server routes**: `verifyAdmin(request)` from `lib/auth.ts` on every route
- **Parallel fetches**: `Promise.allSettled` (not `Promise.all`), return `partial: true` on partial failure, 502 on total failure
- **SWR config**: `components/swr-provider.tsx` — exponential backoff, skip retry on 401/403
- **SWR keys**: `token ? [url, token] : null` — null prevents fetch until auth ready
- **UI on partial**: amber warning. **UI on error**: clear stale data, show N/A — never display old data with error flag
- **Banned**: custom fetchers, `useEffect` token management, direct `fetch()` with manual auth, `Promise.all` for parallel upstream calls, serving zero metrics on upstream failure

## Revenue metrics

Subscription metrics read Stripe through `lib/stripe-subscriptions.ts`. Routes must not list subscriptions by hardcoded price id — that is how five of seven products became invisible to the dashboard.

- **Scope**: `OMI_PLAN_PRODUCTS` in that module lists the subscription plans. Metrics count those products and nothing else — the account also holds marketplace apps and internal test products. Launching a plan adds a line.
- **Marketplace apps** are excluded by `metadata.app_id`, which the backend stamps on app checkouts. Never split them off by price id.
- **MRR** counts `active` + `past_due`. `trialing` is pipeline and is reported separately, never inside MRR.
- **Amounts** normalise through each price's own `interval` and `interval_count`; never assume monthly-or-annual.
