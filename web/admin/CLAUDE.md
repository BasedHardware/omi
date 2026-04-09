# Web Admin Dashboard

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
