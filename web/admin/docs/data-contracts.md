# Web Admin Data Contracts

Detail for the two rules in `web/admin/AGENTS.md`.

## Networking

All fetches use `hooks/useAuthToken.ts`; never call `getIdToken()`, create auth headers, or read Firestore in the client.

- Reads: `useAuthToken()` + `authenticatedFetcher`; mutations: `useAuthFetch()` → `fetchWithAuth(url, init)`.
- Server routes call `verifyAdmin(request)` from `lib/auth.ts`.
- Parallel fetches use `Promise.allSettled`, returning `partial: true` on partial failure and 502 on total failure.
- SWR configuration belongs in `components/swr-provider.tsx`; keys are `token ? [url, token] : null`.
- Partial data shows an amber warning. On error, clear stale data and show N/A; never show stale data with an error flag.
- The wall route alone serves bounded last-good aggregates during refresh or source
  failure, as explicitly requested for kiosk continuity. It preserves refresh
  receipts and dims previous-day or failed-refresh data; other routes retain the
  clear-on-error rule above.
  A retryable partial failure retains the last non-null metric by id with its
  original source receipt. Failed jobs retry after 30 seconds; successful jobs
  keep their own 15-minute TTL, including across retries of another source.
- Do not add custom fetchers, `useEffect` token handling, manual-auth `fetch()`, `Promise.all` upstream calls, or zero metrics for upstream failures.

## Revenue metrics

Subscription metrics use `lib/stripe-subscriptions.ts`; never list subscriptions by price ID.

- `OMI_PLAN_PRODUCTS` defines the subscription scope; it excludes marketplace apps and internal test products. Add a line when launching a plan.
- Marketplace apps are excluded by `metadata.app_id`, stamped by the backend on app checkout.
- MRR includes `active` and `past_due`; report `trialing` separately.
- Normalize amounts with each price's `interval` and `interval_count`; never assume monthly or annual pricing.
