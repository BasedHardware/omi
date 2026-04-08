# Web Admin Dashboard

## Authentication (MANDATORY)

All client-side API fetches MUST use the shared auth layer from `hooks/useAuthToken.ts`. No exceptions.

### Rules

- **SWR data fetching**: Use `useAuthToken()` + `authenticatedFetcher`.
  ```typescript
  const { token } = useAuthToken();
  const { data } = useSWR(token ? ['/api/endpoint', token] : null, authenticatedFetcher);
  ```
- **Manual/mutation fetches**: Use `useAuthFetch()`.
  ```typescript
  const { fetchWithAuth } = useAuthFetch();
  const res = await fetchWithAuth('/api/endpoint', { method: 'POST', body: JSON.stringify(data) });
  ```

### Banned Patterns

- `user.getIdToken()` in components, hooks, or pages — use `useAuthToken()` or `useAuthFetch()` instead.
- `Authorization: Bearer ${token}` header construction — `fetchWithAuth` handles this.
- Custom fetcher functions that duplicate `authenticatedFetcher` logic.
- `useEffect` blocks that only exist to call `getIdToken()` and store tokens in local state.
- Direct Firestore reads from client-side code for admin data — use server API routes instead.

### Why

PR #6412 broke 4 dashboard tabs because components had independent fetch patterns that forgot auth headers. Centralizing auth in `useAuthToken.ts` makes this class of bug impossible — there is exactly one place where tokens are managed and attached to requests.

## Server-Side API Routes

- All admin API routes MUST call `verifyAdmin(request)` from `lib/auth.ts` as the first operation.
- Prefer wrapping routes with a shared auth handler to prevent missed checks.
