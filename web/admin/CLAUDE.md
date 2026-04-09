# Web Admin Dashboard

## Networking Architecture

All data flows through a shared client networking layer. Follow these rules for every new page, hook, or API route.

### Client-Side Data Fetching

All client-side fetches use `hooks/useAuthToken.ts`. No direct `getIdToken()` or manual `Authorization` headers.

- **SWR reads**: `useAuthToken()` + `authenticatedFetcher` — includes 30s timeout + 401 auto-refresh
- **Mutations**: `useAuthFetch()` → `fetchWithAuth(url, init)` — includes 30s timeout + 401 auto-refresh + replay
- **Banned**: custom fetchers, client-side Firestore admin reads, `useEffect` token management, direct `fetch()` with manual auth headers

### Server Routes (API)

- Call `verifyAdmin(request)` from `lib/auth.ts` on every route
- Use `Promise.allSettled` (not `Promise.all`) when fetching from multiple upstream sources
- When any leg fails: return `partial: true` in JSON response so UI can warn
- When ALL legs fail: return 502 error — never serve fabricated zero metrics as 200
- All data reads go through Next.js API routes — no direct Firestore reads from client components

### SWR Global Config

`components/swr-provider.tsx` provides global SWR config. Do not override these in individual hooks unless necessary:
- Exponential backoff retry (2s/4s/8s), max 3 retries
- Skip retry on 401/403 (auth errors need re-login, not retry)
- 5s dedup interval, reconnect revalidation

### UI Error Handling

- When API returns `partial: true`: show amber warning badge/banner ("Numbers may be incomplete")
- When API returns error (502, 500, network): clear stale data, show N/A or error state — never display old successful data alongside an error flag
- Charts: show "Chart data unavailable" instead of empty/loading state on hard failure

### Auth Token Lifecycle

- `useAuthToken()` manages Firebase ID token with 10-min proactive refresh
- Token auto-refreshes on 401 via ref-counted module-level `_forceRefreshCallback`
- Multiple hooks can mount `useAuthToken()` simultaneously — ref-counting prevents unmount races
- SWR keys include token: `token ? [url, token] : null` — null key prevents fetch until auth ready
