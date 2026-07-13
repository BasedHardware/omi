# Running the Windows app in parallel git worktrees

You can run several `pnpm dev` sessions at once, one per git worktree, each with
its own port, its own Electron profile, and (optionally) a signed-in session —
with zero changes to how the primary checkout behaves.

## TL;DR

```bash
# in a fresh linked worktree's desktop/windows:
pnpm bootstrap        # install deps, copy .env, build helpers, print your ports
pnpm dev              # runs on THIS worktree's derived port + its own profile
pnpm seed:auth        # optional: boot signed-in by copying the primary app's session
```

- The **primary checkout** (your main `omi` clone) is unchanged: renderer
  `http://localhost:5179`, CDP `9222`, the default userData profile.
- Each **linked worktree** derives its own renderer port (5180-5279) and CDP port
  (9230-9329) from its folder name, plus its own userData profile
  (`omi-windows-sandbox-<worktree>`) and a ` — <worktree>` window-title suffix.
- Run `pnpm dev:instance` in any checkout to see exactly what it resolves to.

## Creating a worktree

```bash
git fetch origin
git worktree add .worktrees/<name> -b <branch> origin/main
cd .worktrees/<name>/desktop/windows && pnpm bootstrap
```

Branch from **`origin/main`** — `origin` is this repo's fork and its `main` is the
base for all work. `upstream` is the read-only BasedHardware remote; never branch
work from `upstream/main`.

## Why this is needed

In dev the renderer is served by Vite at `http://localhost:<port>`, and the app's
sign-in state persists **per origin**: Firebase auth uses `browserLocalPersistence`
(`src/main/../lib/firebase.ts`), and onboarding/prefs live in `localStorage`
(`omi-windows-prefs-v1`) — both keyed by the renderer's origin, which includes the
port. So a single pinned port means only one dev app can run, and moving to a
different port silently signs you out (new origin = empty localStorage).

Two dev instances therefore need **different ports** (so they don't fight over one)
but that means **different origins** (so their saved sessions don't automatically
carry). This tooling makes both problems disappear: a stable per-worktree port, an
isolated profile so instances never clobber each other, and a one-command seed that
copies the session across origins when you want to skip the web login.

## How instances are derived

`src/main/devInstance.ts` is the single source of truth.

- **Primary vs linked**: a linked git worktree has a `.git` _file_ (a `gitdir:`
  pointer); the primary checkout has a `.git` _directory_. The primary always
  resolves to `{ name: 'primary', rendererPort: 5179, cdpPort: 9222 }` and stays on
  the default profile — nothing about the main flow changes.
- **Ports**: derived from the worktree folder name with the same FNV-1a + avalanche
  hash used for packaged builds (`portDerivation.ts`). Renderer ports land in
  5180-5279, CDP ports in 9230-9329 (a separate band so the two never coincide).
  Deterministic, so a worktree keeps the same port across launches (stable origin =
  stable saved session).
- **Collisions fail loud**: Vite runs with `strictPort`, so if two worktrees happen
  to hash to the same renderer port the second `pnpm dev` errors out instead of
  drifting to a new origin. Set `OMI_DEV_PORT` on one of them to move it.

The Vite config (`electron.vite.config.ts`) sets the dev server port and also
stamps `OMI_INSTANCE` / `OMI_DEV_CDP_PORT` / `OMI_SANDBOX` into the env for the
Electron main process; the main process re-derives from its own cwd as a fallback,
so correctness never depends on that env being forwarded.

## Auth seeding (`pnpm seed:auth`)

`scripts/seed-auth.mjs` copies the signed-in session from a running **source**
instance into a running **target** instance:

1. Connects to the source app's Chrome DevTools Protocol port and reads its
   `localStorage` (the whole signed-in state: Firebase session + onboarding/prefs).
2. Connects to the target app's CDP port and writes those keys into its
   `localStorage`, then reloads the target so Firebase rehydrates the session.

Defaults to **primary (CDP 9222) -> this worktree** (target derived from cwd), so
from a worktree you usually just run `pnpm seed:auth` with the primary app open.

```bash
pnpm seed:auth                         # primary -> this worktree
pnpm seed:auth --to fix-orb            # primary -> the "fix-orb" worktree
pnpm seed:auth --from-port 9267 --to-port 9264   # explicit CDP ports
pnpm seed:auth --auth-only             # only firebase:* + omi-windows-prefs-v1
pnpm seed:auth --dry-run               # show what would be copied
```

### Why CDP, not a file copy

The session lives in the Chromium profile's `Local Storage` leveldb, keyed by
origin (`http://localhost:5179`). A raw file copy into another profile would land
the data under the _wrong_ origin (the target runs on a different port), so the
target renderer wouldn't find it — and leveldb is a single-writer store, so you'd
also have to close the source app first. Reading/writing `localStorage` over CDP is
just JS on each side, so it translates origins naturally and works while both apps
are running (the normal dev state). It reuses the existing `OMI_DEV_REMOTE_DEBUG`
seam, which is dev-only: the packaged app never opens a CDP port
(`dev/bench.ts` gates it on `!app.isPackaged`).

## Environment overrides

| Var                         | Effect                                                                                                                                                                                         |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `OMI_INSTANCE=primary`      | Force the primary instance (5179, default profile) from any worktree                                                                                                                           |
| `OMI_INSTANCE=<name>`       | Force a named instance (ports derived from `<name>`)                                                                                                                                           |
| `OMI_DEV_PORT=<n>`          | Pin the renderer port (e.g. to dodge a collision)                                                                                                                                              |
| `OMI_DEV_CDP_PORT=<n>`      | Pin the CDP port                                                                                                                                                                               |
| `OMI_DEV_REMOTE_DEBUG=<n>`  | Pin the CDP port; **wins over `OMI_DEV_CDP_PORT`** (it is the switch actually bound). `pnpm dev:instance` / `seed:auth` resolve the same precedence, so set it in the shell you run both from. |
| `OMI_SANDBOX=<name>`        | Pin the userData profile suffix (`OMI_SANDBOX=1` = legacy `chat-kg`)                                                                                                                           |
| `OMI_DEV_NO_REMOTE_DEBUG=1` | Don't open a CDP port for this instance                                                                                                                                                        |
| `OMI_DEV_HW_GPU=1`          | Use hardware GPU instead of the dev software-render default                                                                                                                                    |

## Troubleshooting

- **`pnpm dev` errors that the port is in use** — two worktrees hashed to the same
  _renderer_ port. This IS fail-loud (Vite `strictPort`). Set `OMI_DEV_PORT=<free
port in 5180-5279>` on this one.
- **`seed:auth` says it can't reach a CDP endpoint** — the source or target app
  isn't running (or was started with `OMI_DEV_NO_REMOTE_DEBUG=1`). Start it with
  `pnpm dev` in that checkout.
- **`seed:auth` reaches the WRONG app / a _CDP_ port collided** — unlike renderer
  ports, CDP-port collisions are **not** fail-loud: both apps still launch, but the
  second to start fails to bind its CDP port, so it can't be seeded (and CDP tools
  hit the first app). Two worktrees hashing to the same CDP port is the usual
  cause. Fix it by pinning `OMI_DEV_CDP_PORT=<free port in 9230-9329>` on one of
  them (`pnpm dev:instance` shows each instance's resolved CDP port).
- **`seed:auth` warns "no firebase:authUser"** — the source app isn't signed in;
  sign into the primary app once, then re-run.
- **Worktree looks signed-out on first run** — expected: a fresh worktree gets an
  empty profile. Run `pnpm seed:auth` (or just sign in there once).
- **Two windows look identical** — check the title-bar suffix (` — <worktree>`) or
  run `pnpm dev:instance` to confirm which port each is on.

## Notes

- Only linked worktrees auto-isolate; the primary checkout is deliberately left on
  the shared default profile (that's where your real data + session live).
- Everything here is dev-only. Packaged builds serve the renderer from
  `rendererServer.ts` with the per-install port from `portDerivation.ts` and never
  run the dev-instance code.
