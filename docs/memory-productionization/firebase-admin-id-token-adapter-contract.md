# Firebase Admin ID-token adapter contract

Status: pre-registered inert P7 runtime-adapter contract. This unit adds no
route, account mapping, grant, authorized context, production credential, or
deployment activation.

## Dependency and runtime coordinate

Pin the official `firebase-admin` package at exactly `14.2.0`. Its current
published support floor is Node.js 22. The repository remains Bun-first, so the
same import and construction smoke must pass under the pinned Bun 1.3.14 and
the installed Node 22 temporary control before this adapter lands. This is a
local compatibility check, not production-runtime qualification.

Official references refreshed 2026-08-11:

- <https://firebase.google.com/docs/admin/setup>
- <https://firebase.google.com/docs/auth/admin/verify-id-tokens>
- <https://firebase.google.com/docs/auth/admin/manage-sessions>
- <https://firebase.google.com/docs/emulator-suite/connect_auth>
- <https://www.npmjs.com/package/firebase-admin/v/14.2.0>

## Adapter construction

Add one driver-owned factory over the official modular imports from
`firebase-admin/app` and `firebase-admin/auth`. Construction accepts exact
plain configuration containing a bounded project id, a bounded explicit app
name, and the closed runtime mode `deployed | local_test`.

The factory:

1. reads `FIREBASE_AUTH_EMULATOR_HOST` itself before SDK initialization;
2. refuses construction in `deployed` mode when that variable is present,
   including an empty value;
3. initializes one explicitly named Firebase app with both
   `applicationDefault()` and the exact configured `projectId`, never an
   ambient project fallback or embedded service-account payload;
4. obtains Auth only from that exact app;
5. returns an exact plain adapter whose source is derived from the observed
   environment and whose only operation delegates
   `verifyIdToken(token, true)`; and
6. returns a separate idempotent close operation that deletes only the app it
   created and makes later verification fail closed.

The adapter does not parse tokens, authorize a Firebase custom claim, map a uid
to an Omi account, read account control, or create a grant/capability. The
landed identity-only boundary remains responsible for independent
audience/issuer/uid/time validation and output minimization.

Initialization and verification errors may be caught by the caller but no SDK
error message, credential path, token, decoded claim, project id, app name, or
environment value enters logs or a public result. No credential is read during
hermetic tests, and no live Firebase endpoint is called.

## Composition and lifecycle

There is no default or route composition in this unit. A later authenticated
application composition may create exactly one handle at service startup, pass
its adapter into the identity-only verifier, and close the handle on shutdown.
That later unit must still compose Firebase identity with an application-owned
credential binding, exact grant, and coherent account-control admission before
minting an authorized context.

Real signed, revoked, disabled-user, emulator-network, key-rotation, and
provider-outage tests remain release gates. They require explicitly authorized
test infrastructure and credentials and are not replaced by hermetic fakes.

## Pre-registered tests

1. Exact configuration constructs one named app with exact project id and an
   application-default credential, then binds Auth to that same app.
2. Verification delegates the unchanged token with literal `true` exactly once
   and returns the SDK-decoded value unchanged to the identity boundary.
3. A present emulator variable makes deployed construction fail before
   credential, app, or Auth construction; local-test mode alone reports the
   emulator source.
4. Invalid/extra/accessor/proxy/class configuration and invalid project/app
   names fail before SDK work without invoking getters.
5. Construction and verify failures expose no raw sentinel through logs or an
   adapter-owned public error; close is idempotent and later calls fail closed.
6. Two constructions with the same app name fail rather than silently reuse an
   ambient app with potentially different project or credentials.
7. A source scan proves this driver imports no route, account/control, grant,
   repository, memory core, model, filesystem, or service secret module.
8. The runtime smoke imports the exact official package and constructs/deletes
   a local named app under both Bun 1.3.14 and Node 22 without network calls.
