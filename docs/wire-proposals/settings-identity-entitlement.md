# Settings identity and entitlement wire proposal

Status: **proposal for ratification; not a contract and not an implementation**.

This document proposes the server-owned portion of Settings. It adds no route,
store, domain type, or client adapter. `appearance` is deliberately absent from
every server envelope because its authority is shell-local.

Evidence coordinates:

- platform: `d9b91c0f9ab25ad91e45d0b7b8482042f7943534`
- read-only core-foundation: `8e2e1c52b24fb1a80334c700dfb006db827a32a5`
- surface input: `core/packages/surfaces/src/production/settings-merge.ts:1-29`
- surface port: `core/packages/surfaces/src/production/ProductionSettingsStore.ts:19-34`
- account control: `core/control/account-control.ts:1-116` and
  `apps/service/control/projection-store.ts:1-40`

`Entitlement` remains legacy vocabulary pending `UNK-DOMAPPS-001`. Every use of
the proposed wire field `entitlement` below is therefore
`domain-pending(UNK-DOMAPPS-001)`, not a naming ratification.

## Ratified inputs this proposal does not reopen

- `apps/service` owns account identity and entitlement.
- Appearance is shell-local and is not account-scoped server state.
- The authenticated principal, never a request-supplied account id, selects the
  account. The service already follows this rule for account-epoch reads.
- This lane specifies the wire only. It does not create an account or
  entitlement domain type; both are absent today, so Settings is greenfield.

## Shape the client already assumes

`SettingsSnapshot` is:

```ts
type SettingsSnapshot = {
  identity: { displayName: string; email: string } | null;
  appearance: "default" | "system" | "light" | "dark";
  entitlement: {
    planLabel: string;
    limitKey: string;
    used: number;
    limit: number | null;
    limitReached: boolean;
    upgradeAvailable: boolean;
  } | null;
};
```

The client renders entitlement fields as supplied. It does not derive plan
logic. `limit: null` means unmetered. `identity: null` means signed out. The
surface also has `patch({ appearance })` and `signOut()`, but only `signOut()`
crosses this proposed server boundary. Appearance patching and its dead letters
remain shell-local.

## What apps/service would owe

- A coherent read of identity and entitlement for one authenticated account,
  or an explicit signed-out response when the caller supplied no credential.
- Required identity fields whose empty strings remain different from no
  identity.
- An authoritative entitlement absence distinct from an unmetered entitlement.
- Fixed, non-oracular error bodies. No account id, epoch, grant detail, plan
  decision, or upstream exception appears in an error.
- Current-session sign-out with an exact invalidation boundary.
- No appearance read, write, default, revision, or merge behavior.

## Recommended wire

### Route summary

| Route | Auth | Success | Purpose |
| --- | --- | --- | --- |
| `GET /v1/settings` | Optional Bearer | `200` JSON | Read the server-owned Settings fields. |
| `DELETE /v1/session/current` | Required Bearer | `204` empty | Revoke only the session represented by the presented credential. |

Both routes return `Cache-Control: no-store`. JSON responses use
`Content-Type: application/json`. The service reads `x-omi-contract-version`
under the existing app-facing convention; this proposal does not choose the
first contract version containing the wire.

There is no `PATCH /v1/settings`: the only current patch key is appearance, and
putting that route on the service would contradict the settled authority split.

### `GET /v1/settings`

The request has no body and no account identifier. Unknown or repeated query
parameters are `400 bad_request` rather than silently changing future meaning.

No `Authorization` header is the intentional signed-out state:

```json
{
  "identity": null,
  "entitlement": null
}
```

A valid Bearer credential returns the current account fields:

```json
{
  "identity": {
    "displayName": "Alex Rivera",
    "email": "alex@example.com"
  },
  "entitlement": {
    "planLabel": "Omi Plus",
    "limitKey": "memories",
    "used": 42,
    "limit": 100,
    "limitReached": false,
    "upgradeAvailable": true
  }
}
```

The envelope is the server-owned subset of `SettingsSnapshot`, not a second
`settings` wrapper. The adapter adds its shell-local `appearance` value to form
the surface snapshot.

#### Null and empty semantics

- `identity: null` means **no credential was presented** and therefore no
  account is selected. It always pairs with `entitlement: null`.
- An invalid, expired, malformed, or revoked credential is not signed-out
  success. It returns `401 unauthorized`, so credential loss cannot masquerade
  as an intentional local sign-out.
- A signed-in account with no display values is still an object:

  ```json
  {
    "identity": { "displayName": "", "email": "" },
    "entitlement": null
  }
  ```

  Required fields are present even when empty. The service and adapter must not
  coerce that object to `null`.
- `entitlement: null` means the service authoritatively has **no entitlement
  presentation applicable to this account and surface**. It does not mean free,
  zero remaining, unknown, temporarily unavailable, or unmetered. An upstream
  lookup failure returns `503`; it never degrades to `null`.
- Unmetered is a present entitlement with `limit: null`:

  ```json
  {
    "identity": { "displayName": "Alex Rivera", "email": "alex@example.com" },
    "entitlement": {
      "planLabel": "Omi Plus",
      "limitKey": "memories",
      "used": 7,
      "limit": null,
      "limitReached": false,
      "upgradeAvailable": true
    }
  }
  ```

  For an unmetered entitlement, `limitReached` must be `false`. `used` remains
  the server's non-negative observation; the client does not compare it with a
  fabricated limit.

#### Read status and error bodies

| Status | Fixed body | Meaning |
| --- | --- | --- |
| `200` | the exact success envelope above | Signed out by absent credential, or signed in with coherent data. |
| `400` | `{"error":"bad_request"}` | Body, query, or single-valued parameter grammar was invalid. |
| `401` | `{"error":"unauthorized"}` | A credential was presented but could not authenticate a current session. |
| `403` | `{"error":"forbidden"}` | Authenticated, but not authorized to read the bound account. |
| `503` | `{"error":"service_unavailable"}` | Identity or entitlement could not be read coherently; include a fixed `Retry-After`. |

There is no partial `200`. In particular, entitlement infrastructure failure
does not return a valid identity beside `entitlement: null`.

### `DELETE /v1/session/current`

This is the wire operation behind `ProductionSettingsStore.signOut()`.

The request carries the current Bearer credential, no body, and no account id.
On first application it:

1. revokes the one service session represented by that credential;
2. makes later app-facing use of that session fail authentication;
3. expires any service-owned session cookie in the response; and
4. returns `204` with an empty body.

The server does **not**:

- increment or invalidate the account epoch;
- deactivate, delete, or otherwise mutate the account-control projection;
- invalidate other sessions, installations, API keys, app grants, or identity
  provider sessions;
- delete account data, entitlement state, uploads, or queued user writes;
- clear shell-local credentials, appearance, caches, or outbox state; or
- revoke an upstream refresh token unless the presented service session is
  explicitly backed by that token and a later credential-binding contract says
  so.

The shell clears its local credential and composes
`{ identity: null, entitlement: null }` only after it has made the best-effort
server call. Local account-scoped durable data follows the existing
account-switch/outbox rules; sign-out is not authority to discard it.

Repeat delivery after a lost `204` must also return `204` while the service can
recognize the just-revoked session handle. This makes sign-out safe under retry
without widening revocation. A credential that was never a recognizable
service session returns `401`.

| Status | Fixed body | Meaning |
| --- | --- | --- |
| `204` | empty | Current session revoked, or the same revocation replayed. |
| `400` | `{"error":"bad_request"}` | A body or unsupported parameter was supplied. |
| `401` | `{"error":"unauthorized"}` | No recognizable current service session. |
| `503` | `{"error":"service_unavailable"}` | Revocation was not durably recorded; include a fixed `Retry-After`. |

A `503` must not claim success. The shell may still remove local credentials as
a local safety choice, but it must record that server revocation was not
confirmed rather than silently upgrading the result to `204`.

## Reuse and placement recommendation

The existing account-control projection is the right **composition neighbor**
but the wrong record to extend:

- It already selects by authenticated `principal.uid`, carries the account
  generation/epoch/lifecycle coordinates, makes absent control explicit as
  `null`, and is read by the app-facing service.
- Its semantics are deliberately narrow: it is a subordinate copy of
  legacy-published migration control, and `activation` is the only field the
  destination owns. Adding display names or quota counters to that projection
  would mix identity presentation and product policy into a migration fence.
- The existing refusal composition already treats `entitlement` as distinct
  from authentication, authorization, and stale epoch. The Settings read should
  render the same entitlement projection that enforcement consumes, rather
  than creating a display-only answer that can disagree with a later write.

Recommendation: compose the Settings read beside the existing control/fence
ports, using the same authenticated account key and one coherence boundary, but
use sibling identity and entitlement read projections. Entitlement enforcement
can consume the same entitlement projection that Settings renders; it should
not create a Settings-only truth. This is reuse of the account binding and
coherence machinery, not mutation of `AccountControlProjection` and not a new
independent authority subsystem.

Missing migration control must not be translated to `identity: null`; a valid
credential still selected an account. If a coherent Settings answer depends on
control state that is temporarily absent, the honest answer is `503`, not a
signed-out `200`.

## Open choices for ratification

### 1. One read or two reads

- **A — one `GET /v1/settings`** returning identity and entitlement coherently.
- B — separate `/identity` and `/entitlement` reads, composed by the client.
- C — a generic bootstrap document containing these and unrelated domains.

**Recommendation: A.** It matches the surface's one snapshot, avoids a torn
signed-in/entitlement view, and does not make a generic bootstrap resource own
future unrelated fields.

### 2. Signed-out response

- **A — absent credential returns `200` with both fields null; invalid presented
  credential returns `401`.**
- B — every missing or invalid credential returns `401`, and the adapter invents
  the null snapshot locally.
- C — every missing or invalid credential returns the same null success.

**Recommendation: A.** It preserves the surface's intentional signed-out state
without hiding credential expiry or revocation.

### 3. Sign-out scope

- **A — revoke the presented service session only.**
- B — client-only credential deletion with no server route.
- C — revoke every session and credential binding for the account.

**Recommendation: A.** It gives `signOut()` a real, retryable server effect while
avoiding the surprising blast radius of “sign out everywhere.” An all-sessions
operation should be a separately named, separately authorized product action.

### 4. Account-control placement

- A — add identity and entitlement fields to `AccountControlProjection`.
- **B — sibling projections composed through the existing authenticated account
  and epoch boundary.**
- C — a new Settings subsystem with its own account binding.

**Recommendation: B.** A conflates product state with migration control; C
duplicates the binding/fence machinery the repo already owns.

### 5. Envelope wrapper

- **A — `{ identity, entitlement }`.**
- B — `{ settings: { identity, entitlement } }`.
- C — return identity and entitlement from separate top-level resources.

**Recommendation: A.** It is the smallest lossless server subset of the surface
snapshot and leaves `appearance` visibly absent rather than apparently omitted
from a full server-owned Settings object.

## COULD NOT DETERMINE

- The production credential kind, session handle, refresh-token ownership, and
  exact mechanism that makes a revoked session recognizable for idempotent
  replay. The local service currently has only a dev HMAC token seam.
- The authoritative identity source and freshness contract for `displayName`
  and `email`.
- The entitlement projection's source, revision, refresh cadence, and the exact
  set of accounts for which authoritative `entitlement: null` is legal.
- Whether `planLabel`, `limitKey`, and `Entitlement` survive the open domain
  naming decisions. This proposal uses the required legacy surface spellings
  and does not ratify them as domain names.
- The fixed `Retry-After` value and the contract-version number that first
  carries this wire.

These unknowns block implementation details, not evaluation of the route and
envelope recommendation. A ratifier should explicitly accept or replace each
recommended option before any route is added.
