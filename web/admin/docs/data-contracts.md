# Web Admin Data Contracts

Detail for the two rules in `web/admin/AGENTS.md`.

## Networking

All fetches use `hooks/useAuthToken.ts`; never call `getIdToken()`, create auth headers, or read Firestore in the client.

- Reads: `useAuthToken()` + `authenticatedFetcher`; mutations: `useAuthFetch()` → `fetchWithAuth(url, init)`.
- Server routes call `verifyAdmin(request)` from `lib/auth.ts`.
- Parallel fetches use `Promise.allSettled`, returning `partial: true` on partial failure and 502 on total failure.
- SWR configuration belongs in `components/swr-provider.tsx`; keys are `token ? [url, token] : null`.
- Partial data shows an amber warning. On error, clear stale data and show N/A; never show stale data with an error flag.
- Do not add custom fetchers, `useEffect` token handling, manual-auth `fetch()`, `Promise.all` upstream calls, or zero metrics for upstream failures.

## Revenue metrics

Subscription metrics use `lib/stripe-subscriptions.ts`; never list subscriptions by price ID.

- `OMI_PLAN_PRODUCTS` defines the subscription scope; it excludes marketplace apps and internal test products. Add a line when launching a plan.
- Marketplace apps are excluded by `metadata.app_id`, stamped by the backend on app checkout.
- MRR includes `active` and `past_due`; report `trialing` separately.
- Normalize amounts with each price's `interval` and `interval_count`; never assume monthly or annual pricing.
