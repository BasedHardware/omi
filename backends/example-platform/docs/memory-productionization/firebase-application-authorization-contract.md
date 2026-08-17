# Firebase application-authorization composition contract

Status: pre-registered inert P7 implementation of ADR-010's already accepted
single composition path. This creates no new authority class and adds no route,
database adapter, credential issuance, account minting, entitlement, or
deployment activation.

## Authority order

One construction site binds a Firebase identity verifier, an application-owned
credential/grant source, the coherent account-control source, a fixed registered
application id, one exact capability, and a bounded context lifetime. A caller
supplies only a bearer token and an injected epoch-second clock. Request headers,
body fields, Firebase custom claims, and Firebase uid never select application,
capability, owner, credential, grant, or account epoch.

Authorization runs in this order and never speculates around a failed stage:

1. verify the token through the landed identity-only boundary, retaining its
   exact configured Firebase project coordinate;
2. ask the credential/grant source once for the exact configured application
   and capability under that Firebase uid;
3. strictly validate an active head-bound credential and exact active enabled
   grant, including the exact requested Firebase uid binding, principal,
   application, capability, expiry, grant
   version, authorization-state digest, and the control coordinates observed by
   that source;
4. inspect the account through the coherent control source once;
5. require exact agreement on account epoch, control revision, and destination
   activation revision; and
6. only then use the private issuer to mint one short-lived authorized ledger
   context whose expiry is the minimum of token expiry, credential expiry, and
   configured lifetime.

The credential/grant source request is frozen and contains only the verified
Firebase project id and uid, configured application id, and configured
capability. It receives no raw token.
Its `current | absent | unavailable` envelope is untrusted plain data. A current
row is exact-shaped and carries the full repository revalidation coordinates;
the composition copies no raw record or provider detail.

The source's returned Firebase project id and uid must equal the verified pair
and its
authentication strength must be exactly `firebase-id-token`. The source also
returns the separate bounded principal coordinate persisted on the credential;
the composition does not derive it from the uid or require Firebase's broader
uid alphabet to satisfy an internal identifier grammar. The uid is an external
credential binding, never an account id. Account and principal ids are
pre-existing opaque coordinates; this unit does not implement the unresolved
ADR-012 word grammar or mint either one.

## Closed outcomes

The public composition returns exactly one frozen union:

- `authorized`, carrying the runtime-minted context;
- `authentication`, for no valid Firebase identity;
- `authorization`, for absent, inactive, expired, mismatched, or malformed
  credential/grant state;
- `stale_epoch`, for a control snapshot that is stale or disagrees with the
  grant snapshot's exact control coordinates; or
- `unavailable`, for credential/grant or control-source unavailability.

Every refusal is account-free and content-safe. Source throws, accessors,
proxies, classes, extras, unsafe counters, invalid digests, cross-account
coordinates, and issuer failures never expose raw detail. Authentication and
authorization remain distinct so a missing grant cannot create a re-login loop.

This minted context is not sufficient proof for a durable operation by itself.
Every production repository must still lock and revalidate the exact principal,
credential generation, grant version, capability, control revision/epoch,
activation, lifecycle, expiry, and authorization-state digest with its database
clock immediately before replay or write.

## Construction fence

The composition is the only non-test module allowed to import the private
authorized-context issuer. The import-graph tripwire must reject direct,
aliased, namespace, re-export, and dynamic imports of that private module from
every other production TypeScript file. The composition exports only its
sealed authorize operation, never the issuer or raw mint input.

## Pre-registered tests

1. A valid token, exact active binding/grant, and matching admitted control
   snapshot invoke identity, grant source, and control source once in order and
   emit one branded frozen context with minimum expiry.
2. Invalid identity calls neither source; absent grant calls no control source;
   no refusal produces or exposes an account id.
3. Wrong Firebase project/uid binding, malformed principal, application, capability, auth
   strength, lifecycle,
   enabled flag, expiry, account, digest, or unsafe version/counter denies before
   issuer access.
4. Missing, conflicting, legacy, migrating, stranded, unactivated, pending
   deletion, and deleted control never mint; stale or coordinate disagreement
   remains distinct from authorization.
5. Source throw/reject becomes unavailable, while hostile source data becomes
   authorization; raw sentinels never enter the returned bytes or logs.
6. Context expiry is bounded by token, credential, and configured TTL and a
   zero/negative/unsafe lifetime or invalid clock fails before source work.
7. Later mutation of source rows, requests, or config cannot alter the frozen
   request, result, or context.
8. A forged visible context remains rejected by the public context assertion,
   and the PostgreSQL transaction-time revalidation tests stay green.
9. The strengthened import tripwire catches direct, aliased, namespace,
   re-export, and dynamic private-issuer imports outside this composition.
10. No route, repository, SQL, filesystem, environment, Firebase SDK, model, or
    secret module is imported by the composition.
