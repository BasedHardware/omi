# Web Admin Data Contracts

Detail for the two rules in `web/admin/AGENTS.md`.

## Networking

All fetches use `hooks/useAuthToken.ts`; never call `getIdToken()`, create auth headers, or read Firestore in the client.

- Reads: `useAuthToken()` + `authenticatedFetcher`; mutations: `useAuthFetch()` → `fetchWithAuth(url, init)`.
- Server routes call `requireScope(request, scope)` from `lib/auth.ts`, with the scope listed in `lib/route-scopes.ts` (see `docs/team-access.md`).
- Scoped routes serialize JSON only through `AdminIdentity.json` (`lib/auth.ts`). It applies one deep redactor driven by the classification table in `lib/sensitive-fields.ts` — a field of a class is stripped at any depth unless the caller holds the scope that unlocks that class. Adding a field or a class is one line in the table.

  | Class (`id`)   | Field names (plus prefixes)                                                                                                                             | Unlocked by                                         |
  | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
  | `financial`    | money, price, payment, subscription, billing, revenue/MRR/cost, total*earned… (prefixes `stripe*`, `payout`)                                            | `finance:read`                                      |
  | `credentials`  | `api_key`, `client_secret`, `code_verifier`, `mcp_oauth_tokens`, `access_token`, `refresh_token`, `webhook_secret`, `private_key`, `secret`, `password` | nothing — no scope ever returns them to the browser |
  | `user-content` | `comment` (CSAT free text), `transcript`, `memories`, `your_questions`, `all_users_questions` (Chat Lab sampling)                                       | `users:read`                                        |

  Names must mean one thing everywhere (why `token` and `email` are not classified: TV share links serve tokens by design; partner and employee emails are business contacts, not end-user data). `lib/__tests__/sensitive-wall.test.ts` calls every scoped GET handler with fixture data seeded with the whole table and fails if any classified name survives for a caller lacking its scope — including the owner, for credentials — so a new route is covered by responding through `identity.json` and nothing else. A route that must show a locked field to an unscoped caller passes `keep` with a comment and a wall test; no route does today.

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
