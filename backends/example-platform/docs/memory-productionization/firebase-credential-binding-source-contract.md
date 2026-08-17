# Firebase credential binding and authorization-source contract

Status: pre-registered inert P7/P2 expand-only contract. This implements the
already accepted Firebase-identity-to-application-authorization direction in
backend ADR-010. It creates no route, account, credential, grant, control
revision, session, production connection, or deployment activation.

## Problem and boundary

The identity boundary now proves an exact Firebase project+uid pair, and the
single application composition accepts only a strict credential/grant source
envelope. PostgreSQL does not yet have a structural relation from that external
identity to one platform account/principal and one application credential. A
uid-only lookup, an account chosen by request data, or a driver query that
guesses among credential rows would violate ADR-010.

This unit adds only the durable relation and one fixed read operation. The
legacy-origin control observation remains the initial account authority. The
application-owned credential and grant remain separate authority coordinates.
The external identity binding merely connects the verified Firebase coordinate
to those already-ratified coordinates; it cannot activate an account or grant a
capability by itself.

## Expand-only schema

Migration 0012 adds two immutable tables.

`firebase_identity_bindings` is a global ingress registry keyed by the exact
`(firebase_project_id, firebase_uid)` pair. That primary key is the deliberate
exception to the memory ledger's account-first key rule: an external identity
must not map to two tenants. Each row stores exactly one existing opaque
`account_id`, one existing opaque `principal_id`, and the existing subordinate
control revision that witnessed the mapping. The row is insert-once. There is
no update, delete, reassignment, provider-claim, email, phone, or custom-claim
column.

`firebase_application_credential_bindings` is account-scoped and insert-once.
It binds that exact identity root and one server-owned `application_id` to one
existing credential identity. Credential rotation advances the existing
credential head/generation; it never rewrites this binding or the Firebase
identity root. Composite foreign keys prove that the account and principal
match the global identity root and that the credential belongs to the same
account/application. No plaintext token or SDK output is stored.

Both tables have bounded text checks. The migration grants the application role
no direct select, insert, update, or delete on either table. Issuance/import,
legacy reconciliation, lifecycle, and account deletion handling remain later
write-side work and human/runtime gates; this unit seeds no rows.

## Named lookup

One `SECURITY DEFINER` function accepts only:

- verified Firebase project id;
- verified Firebase uid;
- the composition-fixed application id; and
- the composition-fixed capability.

It follows the immutable identity and application binding to the current
credential head, exact credential revision, exact capability grant head and
revision, and current subordinate account-control head/revision. It returns at
most one fixed-shape row containing the coordinates and content hashes needed
to construct the existing strict source envelope and the same
authorization-state digest that the final PostgreSQL transaction revalidates.

No caller supplies account, principal, credential, grant, generation, epoch, or
control coordinates. Missing or non-unique state yields no authorization. The
function does not filter away inactive/revoked/deleted/conflicting state: those
closed fields are returned for the existing composition to deny, and the final
repository must still lock and revalidate them with the database clock before
replay or mutation.

The ordinary application role receives execute on this exact function only for
the new tables. Public access is revoked and the function fixes its search path
to `pg_catalog, omi_memory` with fully qualified authority relations.

## Inert driver

The PostgreSQL driver exposes one factory implementing the existing
`FirebaseApplicationAuthorizationSource`. It receives a narrow injected query
capability, executes one immutable named statement, and never exposes that
query capability to the service composition. It accepts only an exact frozen
source request, binds the four values unchanged, and returns exactly:

- `current`, detached to the existing strict envelope and carrying a digest
  computed from the exact returned authority hashes;
- `absent` for zero rows; or
- `unavailable` for query failure, malformed/multiple rows, or digest failure.

Provider messages, SQL text, hashes, account ids, and raw rows never enter an
error or log. The driver does not initialize a pool, read environment, choose a
database URL, create a route, mint a context, or activate PostgreSQL. A real
adapter remains blocked on the ratified PostgreSQL major/client and the real
`bun run test:postgres` gate.

## Pre-registered tests

1. The migration manifest is gap-free and checksums exact 0012 bytes.
2. The global project+uid primary key prevents cross-account duplicate
   identity mappings; the account/principal witness and application credential
   relations are composite foreign keys to exact existing authority rows.
3. Neither new table receives application-role DML/select privileges. Public
   function access is revoked and only the fixed function is executable.
4. Static SQL proves that the caller cannot supply account, principal,
   credential, grant, generation, epoch, lifecycle, or control coordinates and
   that every joined authority relation is exact and fully qualified.
5. A valid single row becomes the exact `current` envelope and its digest is
   byte-identical to final transaction revalidation over the same hashes.
6. Project or uid changes alter the four bound query values; neither uid alone
   nor request metadata can select an account.
7. Zero rows becomes `absent`; multiple, malformed, accessor, proxy, class,
   extra-key, unsafe-counter, wrong-project/uid/application/capability, or bad
   hash rows become `unavailable` without invoking hostile accessors.
8. Query rejection and raw provider sentinels produce only the closed
   `unavailable` envelope and no log/output leakage.
9. Requests and outputs are frozen/detached; later input or row mutation cannot
   retarget the selected authority.
10. Source scans prove no route, Firebase SDK, filesystem, environment, model,
    secret, authorized-context issuer, account mint, or migration runner enters
    the driver.
11. Focused migration/source/composition/transaction tests, strict changed-file
    TypeScript, import-graph lint, the broad hermetic suite, isolated epoch
    fence, and `git diff --check` pass. No fake/static check is reported as real
    PostgreSQL execution.
