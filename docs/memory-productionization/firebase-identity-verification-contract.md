# Firebase identity-only verification contract

Status: pre-registered production-neutral P7 contract. No application grant,
authorized context, route, production credential, Firebase initialization, or
runtime composition is implemented here.

## Sources and accepted authority

ADR-010 §2 decides that Firebase verifies identity only. It does not prove the
calling app, credential generation, capability, grant lifecycle, account epoch,
or account ownership.

Firebase's current official server-verification contract requires a client ID
token to be correctly signed and unexpired, with `aud` equal to the exact
Firebase project id, `iss` equal to
`https://securetoken.google.com/<projectId>`, nonempty `sub`, past `iat`, and
past `auth_time`. Revocation is not checked by ordinary verification; the
Admin SDK must be called with `checkRevoked=true`, which also surfaces disabled
users. Firebase's Auth emulator makes the Admin SDK accept unsigned tokens when
`FIREBASE_AUTH_EMULATOR_HOST` is set, and Firebase explicitly says not to set
that variable in production.

Official references, refreshed 2026-08-11:

- <https://firebase.google.com/docs/auth/admin/verify-id-tokens>
- <https://firebase.google.com/docs/auth/admin/manage-sessions>
- <https://firebase.google.com/docs/emulator-suite/connect_auth>

## Decision

Add an inert asynchronous identity verifier around an injected Firebase Admin
verification adapter. Construction binds an exact project id and a closed
runtime mode (`deployed` or `local_test`). The adapter declares whether it is a
production Firebase verifier or the Auth emulator. A deployed verifier refuses
emulator construction before any token is inspected.

For each bounded JWT-shaped bearer token the boundary calls the injected
adapter exactly once with `checkRevoked=true`. It then independently validates
and detaches the returned decoded claims:

- `aud` equals the configured project id;
- `iss` equals the exact secure-token issuer for that project;
- `sub` is nonempty and equals `uid`;
- `exp` is a future safe epoch second;
- `iat` and `auth_time` are safe epoch seconds not in the future; and
- all inspected claims are own enumerable data, never accessors, proxies,
  classes, symbols, or inherited aliases.

Success returns only a frozen Firebase identity containing the Firebase uid,
the fixed authentication strength `firebase-id-token`, and token expiry. It
does not copy email, phone, provider data, custom claims, raw token bytes, or
adapter metadata. Verification throw/rejection, revoked/disabled user,
malformed claims, wrong project/issuer, expiry, future time, and deployed
emulator mode all return the same `null` authentication result without raw
error logging.

The Firebase uid is an external credential binding, not the ADR-012 account
identifier. No code in this unit may map it to an owner, read control state,
look up a credential/grant, authorize a capability, construct
`AuthorizedContext`, or access a repository.

## Compatibility and exclusions

The existing HMAC `dev1` verifier stays the explicit loopback QA identity
fixture. This unit does not replace or weaken it. A future composition chooses
the Firebase adapter in deployed modes and the dev fixture only in explicit
local/QA modes.

No `firebase-admin` dependency or concrete SDK adapter is selected in this
unit. That adapter must later prove Bun and temporary Node LTS parity, pin
project initialization, refuse ambient emulator configuration in deployed
modes, contain key/network errors, and pass real signed/revoked/disabled token
tests before route activation.

## Pre-registered tests

1. Exact project/issuer/subject/time claims return one frozen identity after
   one adapter call with `checkRevoked=true`.
2. Wrong audience, issuer, uid/sub mismatch, empty/oversized subject, expired
   token, future issue/auth time, unsafe counters, malformed token, and hostile
   decoded objects all return byte-identical `null`.
3. Adapter throw and rejection return `null` and never copy a sentinel error.
4. A deployed runtime rejects an emulator adapter at construction; local test
   mode may use it and may accept the emulator's unsigned JWT shape only through
   that adapter.
5. Production mode requires a nonempty JWT signature segment before the
   adapter; local emulator mode is the only configuration that may present an
   empty signature segment.
6. Adapter-returned custom claims, email, provider, and token mutation cannot
   alter the detached identity or enter its bytes.
7. Config/dependency accessors, proxies, extras, invalid project ids, invalid
   runtime/source kinds, and invalid clocks fail closed without token work.
8. The module imports no route, control source, grant, repository, database,
   filesystem, environment, network, model, or credential secret.
