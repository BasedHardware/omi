# Typed HTTP outcomes — C3 / C4

Builder: App core. Skeletons change no app behavior. Protected acceptance is
`app/test/spine/c3_*`; remove only pending markers. Evidence: outage-as-empty
`cfaaaf2fb9db`, detail null conflation `06597a0757cb`, locked Processing
`92738118b013`, and terminal lookback retry `8a12cfdcca38` (#10975).

## Boundary and taxonomy

`ApiResult<T>` is success(data, rejectedRows) or failure(ApiProblem). A null result
is impossible. `executeApi` reuses shared.dart's headers, pool, timeout, clock-skew
and **existing** `AuthTokenResult`/401 refresh-and-replay. Extract its uncaught send
path once for both old and typed APIs; do not wrap nullable `makeApiCall` and
invent a cause. No new HTTP client, cache, auth owner or implicit retry scheduler.
Unexpected programming errors propagate; known transport failures are classified.
Decode errors are caught only in decoding, not around arbitrary application work.

| Outcome | Result / UI / retry |
| --- | --- |
| DNS/socket/TLS/timeout/client transport exception | transport; error; bounded/manual retry |
| Missing user/token or AuthTokenTerminalFailure; final rejected 401 | authTerminal; authenticationRequired; existing AuthService owns expiration |
| AuthTokenTransientFailure | authTransient; error retaining account; retry; never sign out |
| 404 | notFound; terminal unavailable detail, never transport/empty list |
| 403 | forbidden; terminal access-denied; never notFound |
| 402 | paymentRequired; locked; stop processing/polling; retry only after entitlement change or explicit refresh |
| 422 | unprocessable; terminal rejection (including lookback); stop processing/retry, retain unsent WAL and expose recovery/export |
| 429 | rateLimited; error; honor valid Retry-After (seconds or HTTP date); absent/invalid header uses existing bounded backoff |
| 5xx | server; error; bounded/manual retry |
| malformed JSON/envelope or all rows malformed | decode; error; manual refresh, no automatic loop |
| other non-2xx (including 400/409/redirect) | rejected; terminal; endpoint-specific handling may refine in its migration |
| valid 2xx decoded empty list | success; empty UI |

Retryable is permission for an existing bounded policy, not an instruction to
retry forever. 402/422 never erase local recordings or mark them uploaded.
Not-found conversion to a deleted-record tombstone is endpoint policy, never a
nullable generic API. 204 handling belongs to the endpoint's explicit decoder.

## Consumers and degraded data

First consumer: `api/conversations.dart` plus its real ConversationProvider and
ConversationsPage status region. `composeTypedConversationProvider` must wire the
real provider; `forceRefreshConversations` invokes `ConversationApi.list`.
The provider exposes `apiViewState`; the extracted `ConversationApiStatus` renders
it before existing empty/loading branches, with localized accessible copy and a
retry action only when permitted. Use existing translations with App UI help;
no raw server detail or exception text in UI. Status keys: `omi.conversations.error`,
`.locked`, `.terminal`, `.auth`, `.empty`; error region is a Semantics liveRegion.
A failed first load never shows the new-account hero. A transient/decode failed refresh retains
known data with an error indicator; it never silently calls stale data fresh.
Terminal auth/access/entitlement failures remove protected data from the view
projection (retaining a list row is not permission to render its private body).
402/422 detail/lifecycle consumers transition out of Processing and do not poll
that record again until an explicit eligible state change.

Parse a list envelope once and each row independently. Keep valid rows in order;
count rejected rows without recording ids/content. Partial data is visible with
an incomplete-data indication, never an empty success. All-invalid nonempty
input is decode failure. Do not hide malformed envelopes with `whereType`.

On partial decode or continued stale data, call the shared mobile `recordFallback`
exactly once per completed request, with component/area=`other`, from=`none`,
to=`none`, reason=`other`, outcome=`degraded`; closed mobile reason is carried by
an additional bounded `mobile_reason` field. The wire event is
`fallback_triggered`, through existing AnalyticsManager, with an injected sink in
tests. These conservative shared labels avoid inventing unreviewed global enum
members. Hard failure with no continuation is not fallback telemetry. No raw
body, token, URL, uid, transcript, memory or exception message may reach this helper.
Spine C7 will register this event/consumer, not replace the helper.

## Migration and enforcement

C3 PRs: core types/shared uncaught send and mapper tests, then one API file with
its directly affected consumer state/UI. C4 migrates the other API files one per
PR, updating that file's callers and preserving successful wire/auth/cache
behavior; do not convert all 28 caller files together. Old and new entrypoints
coexist only during this explicitly authorized migration. Existing typed memory
and conversation wrappers keep their failure semantics until moved; deleting
those protections to fit the new type is forbidden. Remove obsolete old wrappers
once their last caller migrates. No broad null-to-empty compatibility adapter.

`app/contracts/api-result/boundary-baseline.json` uses the shared mobile boundary scanner: no growth in
legacy `makeApiCall` invocations and `return null` / `?? []` / `catch` in the
current caller inventory and API directory, compared with base and baseline.
Changed files only; new API files start at zero. This deliberately conservative
lexical tripwire can flag unrelated nulls/catches in those files; migrate or move
error classification to the typed boundary, never inflate debt. Aliases,
helper-wrapped swallowing and success-shaped defaults can evade it; behavioral
contracts remain authoritative. Syntax counts are not an error-flow analyzer.

Out of scope: streaming/multipart redesign, generic UI replacement, auth/cache
rewrite, and migrating every endpoint in the first PR. Native/device acceptance
is separate from hermetic loopback fixture tests.
