# Running the local stack

Commands below are from this repository root. The headed app talks to a
loopback Bun service and a loopback Chat gateway. It does not talk to a
hosted deployment. Shape: [`docs/architecture.md`](architecture.md).
Lanes: [`docs/verification.md`](verification.md).

## Boot the stack

Service on 4851, canned Chat gateway on 8788, SQLite QA database under the
run directory:

```bash
integration/dev-stack.sh --up
```

`--up` is service-only: no surface build, no native shell
(`integration/dev-stack.sh:60-62, 479-480`). It refuses if 4851 or the
chosen gateway port (8788, or 8791 when `OMI_CHAT_MODEL=real`) is already
occupied. It will not kill the occupant or pick another port
(`dev-stack.sh:330-346`). Occupied 5290 is a loud refusal on the assert
path, not on `--up` (`dev-stack.sh:348-357`).

Stop:

```bash
integration/dev-stack.sh --stop
```

`--stop` cannot be combined with a run mode (`dev-stack.sh:64-67`).

The service binary itself, without the stack wrapper:

```bash
bun run apps/service/bin/dev-server.ts
```

Zero environment variables are required. The process binds `127.0.0.1`
only, seeds the QA fixture, prints a loopback bearer, and calls
`ensureLocalOwnerWriteReady` so platform writes have an activated account
epoch (`apps/service/bin/dev-server.ts:46-54, 342-365`). SQLite here is QA
fixture storage, never production authority (`dev-server.ts:61-63`).

## Launch the app

One command:

```bash
bun run app
```

That is `integration/dev-app.sh` (`package.json` script `app`). If 4851 and
8788 are already serving, it reuses them. Otherwise it boots
`dev-stack.sh --up` with `OMI_SEED_PERSONA=demo` (`dev-app.sh:83-85`) and
launches the headed macOS shell at origin `http://127.0.0.1:5290`, route
home (`dev-app.sh:17-20, 147-153`). Chat generation goes through the local
test gateway on 8788, not a real model, unless `OMI_CHAT_MODEL=real`.

Headless-safe check of the same launcher:

```bash
integration/dev-app.sh --accept
```

That mode snapshots the WKWebView and counts host-observed HTTP. It is not
control-acceptance. Clicks live in
`node integration/control-acceptance/run.mjs` — see
[`docs/verification.md`](verification.md).

## Seed the demo persona

`OMI_SEED_PERSONA=demo` overlays the fictional Demo User week on the same
seed machinery (`apps/service/qa/demo-persona.ts:23-31`). Unset, every
seeded QA byte stays the historical fixture. `bun run app` turns the
persona on for a stack it boots; a stack you already started without the
variable keeps the historical fixture.

Demo identity is **Demo User** with empty email
(`demo-persona.ts:37-38`). Expect Harborline Cafe / Cedar Loop / Fable and
Wick people and places, conversations with transcripts in a few folders,
tasks (some linked to those conversations), and a short chat history.

## Reset

`POST /v1/qa/reset` with the loopback bearer restores the deterministic
seed (`apps/service/routes/qa.ts:66-81`). The handler calls `resetSeed`,
which is `reseed` in `apps/service/app-facing.ts:602-617`:

1. `resetServiceStores()` — including `stores.control.reset()`
   (`app-facing.ts:560-576`)
2. `seedQaSnapshot` — memories corpus
3. `seedServiceStores()` — lifecycle, folders, one conversation, settings
   (`app-facing.ts:578-599`)
4. optional persona overlay
5. producer-evidence reset

`GET /v1/qa/status` (no auth) reports served counts and seed identity
(`qa.ts:53-64`). After the app loads a collection,
`domainReadsServed` must be greater than zero or the UI is not talking to
this backend.

Copy the bearer from the boot banner. Do not commit it.

## Known sharp edge: reset wipes the account epoch

This is current behaviour. A sibling lane may fix it. This paragraph
describes the tree today, not the fix.

`stores.control.reset()` returns every account to "never told about"
(`apps/service/control/projection-store.ts:41-64`). Missing control state
denies writes (`projection-store.ts:13-17`;
`core/control/write-fence.ts:134-147` maps that to `control_unavailable`).

`reseed` does not restage the projection. `seedServiceStores` writes
lifecycle, folders, a conversation, and settings; it does not observe or
activate an epoch (`app-facing.ts:578-599`).

The headed process restages exactly once, after
`createLocalDevService`, in `bin/dev-server.ts:342-365`
(`ensureLocalOwnerWriteReady` in `apps/service/qa/local-owner-cutover.ts`).
The helper is deliberately not inside the factory, so in-process tests keep
a missing projection to restage (`local-owner-cutover.ts:7-11`).
`POST /v1/qa/reset` therefore leaves the running process with no
account-control row.

What the user sees next:

- `GET /v1/tasks` omits `accountEpoch` when the projection is null
  (`routes/tasks-read.ts:184-194`).
- The platform Tasks store refuses to journal a create without an observed
  epoch (`frontend/packages/testkit/src/test/platform-tasks-store.test.ts:215-221`).
- The write door, if reached, fails closed on `control_unavailable`.

Only a process restart recreates the projection, because that is the only
call site of `ensureLocalOwnerWriteReady`. The sqlite-reset proof asserts
the wipe: after `/v1/qa/reset`, `stores.control.read(OWNER)` is `null`
(`apps/service/app-facing-sqlite-reset.test.ts:161-174`).

Until a fix lands: after a QA reset, stop and boot the stack again before
expecting Tasks writes to apply.

## Opt-in real Chat model

Default remains the canned gateway. `OMI_CHAT_MODEL=real` selects the local
real-model proxy on 8791. How to tell the two apart is
[`docs/chat-provenance.md`](chat-provenance.md). Do not treat the opt-in as
production. A sibling lane is proving that path; a canned L3 is not that
proof.

## Prod-local (hosted kernel on this machine)

`bun run prod-local` is the Firebase/PostgreSQL memory process, not this
SQLite QA server. See `docs/memory-productionization/prod-local-identity.md`
and [`docs/architecture.md`](architecture.md). It also wants 4851. Do not
run it at the same time as `dev-stack.sh --up` without `--lease`.
