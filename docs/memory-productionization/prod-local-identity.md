# Prod-local emulator identity

Opt-in only. The default `bun run prod-local` path is unchanged: deployed
Firebase identity, no Auth emulator, and the verbatim banner

`omi prod-local: Firebase identity cannot be minted locally.`

`--local-identity` (or `OMI_PROD_LOCAL_IDENTITY=emulator`) is the one local
exception. It requires `FIREBASE_AUTH_EMULATOR_HOST`, composes
`runtime_mode=local_test` with the official Admin verifier, and prints

`omi prod-local: emulator identity — not production.`

Without the flag, a present emulator env still fails with
`PROD_LOCAL_EMULATOR_FORBIDDEN`. Production paths are not weakened.

The minted `idToken` is an emulator JWT, worthless off this machine.

## Prerequisites

1. Managed PostgreSQL harness up:

   ```sh
   bun run test:postgres:setup
   bun run test:postgres:status
   ```

2. Qualification generation **released**, not faked. Readiness 503 has a second
   cause besides identity: `drivers/postgres/production-runtime-readiness.ts`
   requires the released generation digest. Release it by running the real-PG
   gate against the preserved volume:

   ```sh
   bun run test:postgres:preserve
   ```

   The seed script refuses if that digest is absent. It will not insert a fake
   restore-admission row.

3. Loopback port **4851** free for `bun run prod-local` itself. If bind fails,
   believe `lsof` first. `scripts/prod-local-identity-e2e.ts` still proves the
   same fetch handler when 4851 is already leased:

   ```sh
   lsof -nP -iTCP:4851 -sTCP:LISTEN
   ```

## Recipe (this is the acceptance test)

```sh
# 1. Owned Auth emulator for project omi-local-pg (auth only, fixed port 19099).
bun run scripts/prod-local-identity.ts --start
export FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:19099

# 2. Mint an emulator user. The printed bearer is an emulator artifact.
bun run scripts/prod-local-identity.ts --mint
# copy uid and Authorization: Bearer …

# 3. Seed revision+head authorization rows for that uid / app:omi-local-pg.
bun run scripts/prod-local-identity-seed.ts --uid <uid>

# 4. Boot the production process in local-identity mode.
bun run prod-local --local-identity

# 5. Authorized memories.read (expect 200). Unseeded uid (mint a second user,
#    do not seed it) is denied.
curl -s -H "Authorization: Bearer <idToken>" "http://127.0.0.1:4851/v1/memories?limit=5"
curl -s http://127.0.0.1:4851/health
curl -s http://127.0.0.1:4851/ready
```

One-shot proof of the same recipe, including teardown:

```sh
bun run scripts/prod-local-identity-e2e.ts
```

Stop the owned emulator (no orphans):

```sh
bun run scripts/prod-local-identity.ts --stop
lsof -nP -iTCP:19099 -sTCP:LISTEN
pgrep -f /Volumes/Ephemeral/scratch/omi-prod-local-identity/firebase.json
```

Port **19099** is the owned Auth emulator. 9099 is the Firebase default and is
often already leased on this machine by an unrelated harness; this script does
not take it.

## What the seed writes

The seed is the same SQL surface as `postgresjs.real.test.ts`: `platform_accounts`,
`account_control_revisions` + `account_control_heads` (lifecycle `active`),
firebase credential (`strength` `firebase-id-token`), grant `memories.read`,
`firebase_identity_bindings`, and `firebase_application_credential_bindings`
for application `app:omi-local-pg`. Idempotent on those primary keys. Owner
role inserts; lookup is verified as `omi_platform_application`.
