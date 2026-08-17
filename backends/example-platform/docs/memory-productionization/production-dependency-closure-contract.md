# Production dependency closure contract

Status: pre-registered, production-neutral P8 boundary.

## Problem

The frozen development lock contains `uuid@9.0.1`, which is reported by
GHSA-w5hq-g745-h8pq. Its only path from this application is Firebase Admin's
optional `@google-cloud/storage` dependency (and Storage's dependency graph).
The service imports only `firebase-admin/app` and `firebase-admin/auth`.

Firebase Admin 14.2.0 requires `google-auth-library@^10.6.2`; that required
Auth path resolves to gaxios 7 and does not install `uuid`. Its optional
Storage 7.x range requires gaxios 6 and google-auth-library 9, whose compatible
published closure still installs vulnerable `uuid`. A forced transitive
override would violate the declared package ranges and is rejected.

## Frozen production-install decision

The candidate production dependency layer MUST be created from the committed
`package.json` and `bun.lock` with exact Bun 1.3.14 using:

```text
bun install --production --omit optional --frozen-lockfile
```

This is an artifact-construction rule, not a claim that the development lock
or a normal developer install is audit-clean. The lock deliberately retains
Firebase Admin's optional dependency metadata for reproducibility.

## Acceptance invariants

Before any candidate image can pass dependency qualification:

1. The installed tree contains exactly Firebase Admin 14.2.0 and Hono 4.12.34.
2. No installed package is named `uuid`, `@google-cloud/storage`, or
   `@google-cloud/firestore`.
3. No installed package uses the legacy optional-path coordinates
   `gaxios@6.x` or `google-auth-library@9.x`.
4. Application source contains no import of Firebase Storage or Firestore and
   no import of the corresponding Google Cloud packages.
5. `firebase-admin/app` plus `firebase-admin/auth` initialize and dispose under
   both the candidate Bun runtime and the temporary Node LTS control without
   credentials or network access.
6. The verifier examines the physical installed tree, not only the lockfile or
   top-level symlinks. A package retained in an isolated package store fails.
7. A missing, malformed, unreadable, duplicated, or version-mismatched required
   package fails closed with content-safe diagnostics.
8. The exact Linux image must rerun the verifier after the final dependency
   copy. A host-local omitted-optional install is evidence for this bounded
   closure only; it does not satisfy the image/runtime/release gate.

## Exclusions and gates

- No dependency override, Firebase Admin fork, or unratified package upgrade.
- No Storage or Firestore functionality is promised by this service artifact.
- No runtime selection, Docker/Cloud Build choice, image publication,
  deployment, credentials, traffic, or infrastructure mutation.
- Adding Storage or Firestore later requires a new dependency and security
  review; it may not silently remove `--omit optional`.
- Repository-level `bun audit --production` may continue to report optional
  lock metadata. Release evidence must separately report lock audit and exact
  installed-artifact closure; neither result may be relabeled as the other.

## Verification plan

- Add a deterministic, runtime-neutral installed-tree verifier with fixture
  tests for isolated and hoisted layouts, symlink loops, malformed manifests,
  duplicate required packages, forbidden nested packages, and version drift.
- Run it against a fresh archived checkout installed with the frozen command.
- Run the credential-free Firebase Auth construction smoke under Bun and Node.
- Rerun focused service/route tests, the broad platform gate, contract QA,
  import graph, diff check, frozen development install, and both lock audit and
  exact installed-tree verification.
