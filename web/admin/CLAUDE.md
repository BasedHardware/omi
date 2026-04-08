# Web Admin Dashboard

## Auth

All client-side fetches use `hooks/useAuthToken.ts`. No direct `getIdToken()` or manual `Authorization` headers.

- **SWR reads**: `useAuthToken()` + `authenticatedFetcher`
- **Mutations**: `useAuthFetch()` → `fetchWithAuth(url, init)`
- **Server routes**: call `verifyAdmin(request)` from `lib/auth.ts`
- **Banned**: custom fetchers, client-side Firestore admin reads, `useEffect` token management
