# Network fence — proposal for ratification

Status: **proposal for David to rule on; not an implementation**. This
document exists because Rule 18 does not do what a reader of its old
comment would have believed. Building a host-level fence tonight is out
of scope.

Related, already true, and not restated here except to locate the gap:

- What Rule 18 actually is: [`docs/architecture.md`](architecture.md)
  ("Two sanctioned network destinations")
- The import-closure fence itself: `scripts/lint-import-closure.ts`,
  traced by `scripts/trace-value-imports.ts`

## The policy, and the gap

The service is allowed to leave the machine for **Firebase
Authentication** and **the chat model provider**. Nothing else is a
sanctioned leak ([`docs/architecture.md`](architecture.md)).

Rule 18 (`bun run lint:closure`) is the import-closure fence. It walks
the transitive **value-import** closure of the ratified entrypoints and
matches `--forbid` path-substrings against that closure. Type-only
imports are excluded because they erase at runtime. That is real and
load-bearing: a production image cannot link `drivers/model/glm`,
`drivers/model/codex` (LOCAL), `harness/`, `spikes/`, or `migration/` and
still pass. Two defects of exactly that shape have already shipped past
the port-registry and wire-path fences (a model fake via `apps/qa`, the
GLM client via predicate-batch). Rule 18 is the ratchet that made them
unshippable.

It does not observe network traffic. It does not inspect `fetch` URLs,
environment values, or which host a running process contacted. An inline
`fetch("https://anything.example")` written in a module already on an
allowed closure links no forbidden directory, so `lint:closure` stays
green. Confirmed against `scripts/trace-value-imports.ts`: the tracer
matches `import … from "…"` value imports, resolves relative specifiers
to files, and substring-matches those file paths. It never reads a URL.

The rest of this document is the fence that would close that hole.

## Scope the follow-up must not blur

Three processes are easy to collapse and must not be:

1. **The Rule 18 service processes.** LOCAL:
   `apps/service/bin/dev-server.ts`. CLOUD:
   `drivers/postgres/firebase-authorized-memory-service-process.ts`,
   `firebase-authorized-memory-service-app.ts`, `apps/mcp/bun-http.ts`.
   These are the subjects. The local process talks to a loopback
   gateway; it does not link a model client
   (`dev-server.ts` `OMI_LLM_GATEWAY_URL`,
   `createGatewayChatGenerationSource` in
   `apps/service/chat/generation-source.ts`). Firebase identity is
   composed on the hosted memory path, not on the local QA binary
   (`docs/architecture.md`).
2. **The loopback chat gateway.** Canned
   (`integration/local-test-gateway.mjs`) or opt-in real-model proxy
   (`integration/local-model-gateway.mjs`, `OMI_CHAT_MODEL=real`,
   default upstream `https://api.z.ai/api/paas/v4`). This process is
   **not** a Rule 18 entrypoint. When the proxy is selected, *it* is
   the chat-model leak. Observing "the stack" and treating that
   upstream as a violation would fire on the sanctioned path.
3. **The headed shell.** macOS WKWebView against the leased origin
   (`127.0.0.1:5290` / the L3 lease). iOS custom-scheme probe pages
   under `frontend/shells/ios/surface/` fetch third-party echo hosts
   on purpose (ATS/CORS research). They are not the service.

A fence that cannot say which of those three it is watching will be
muted within a week. The first version watches (1) only.

## Candidate A — host allow-list at the call layer

Wrap `fetch` (and only `fetch`, in v1) at each Rule 18 entrypoint,
before the rest of the process runs, and refuse any request whose
destination host is not on a David-only allow-list.

**What it catches.** The stated gap: an inline `fetch` to an
unsanctioned host from a module already on the closure. The same wrap
also catches a misconfigured `OMI_LLM_GATEWAY_URL` that is not
loopback — today that URL is taken as a string
(`generation-source.ts` `gatewayEndpoint`,
`probeGatewayEngineIdentity`) and Rule 18 cannot see it. Production
chat uses `options.fetch ?? fetch`
(`generation-source.ts`), so wrapping the global is the seam the live
path actually uses.

**What it misses.** Anything that does not go through that `fetch`:

- `firebase-admin` ID-token verification
  (`drivers/firebase/admin-id-token.ts`) talks to Google through the
  Admin SDK's own HTTP stack, not through the chat `fetch` seam. A
  wrap of global `fetch` may never see a Firebase revocation check.
- PostgreSQL (`postgres.js`) is TCP, not HTTP.
- `node:http` / `node:https` / `net.Socket` / `Bun.connect`.
- `child_process` (the opt-in MLX Whisper worker is a subprocess of
  the local entrypoint; it is not a `fetch`).
- Tests that inject a `fetch` into
  `createGatewayChatGenerationSource` bypass the global on purpose.
  That is the hermetic seam; it is not a miss of the production path.

**What it breaks if scoped wrong.**

- A Bun `--preload` on `bun test` would wrap every test process.
  Tests construct `Request`s with hosts like
  `route-hardening.invalid` and `service.invalid` and pass them to
  `app.fetch` (in-process Hono). Those must keep working. Some tests
  also call global `fetch("http://127.0.0.1:…")` against a spawned
  server (`dev-server.test.ts`, `bun-http.test.ts`). Loopback must
  be allowed, and the wrap must **not** be a test-runner preload.
  Install it in the four entrypoints only.
- `apps/service/net/assert-loopback.ts` deliberately `fetch`es
  `http://<lan-ip>:<port>/health` and requires those attempts to
  fail. It is not a Rule 18 entrypoint. If the wrap is entrypoint-
  scoped, this script is untouched. If the wrap is a global preload,
  the probe cannot tell "the server is not on the LAN" from "our
  fence blocked the probe", and a correct loopback bind becomes
  indistinguishable from a muted check.

**Cost to build.** Small, if v1 is loopback-only and entrypoint-
scoped. The wrap has to run before any other import that might
`fetch` at module load (`probeGatewayEngineIdentity` runs during
`dev-server.ts` boot). A module that `fetch`es at import time before
the wrap is installed is a bypass; the follow-up lane must prove
there is no such import on the four closures, or install the wrap
via a tiny first-import that those entrypoints load before anything
else.

**Cost to live with.** The allow-list is the product. See "Keeping
the list honest" below. Wrapping only `fetch` is an honest v1: it
closes the gap that Rule 18's comment used to claim, and it names
the SDK/TCP hole instead of pretending to cover it.

## Candidate B — booted-stack test on observed connections

Boot the local (and, separately, prod-local) process, drive a canned
path, and assert that the **service pid**'s established peers are
only the allowed set. Mechanism candidates already in-tree:
`lsof` is how `assert-loopback.ts` proves the listener is
loopback-only. A peer assertion would be the outbound dual of that.

**What it catches.** Traffic the call-layer wrap cannot see:
`firebase-admin` HTTPS, `postgres.js` TCP, a future native addon, a
`child_process` that inherits the parent's network. It answers "what
did this process actually contact?" rather than "what did this
`fetch` call look like?"

**What it misses.**

- Any path the canned drive does not exercise. Default Chat is the
  canned loopback gateway (`docs/architecture.md`,
  `docs/verification.md`, upstream). A green L3 with the canned gateway does
  not prove the real-model proxy, and must not be quoted as if it
  did. Hosted Firebase revocation is not on the local QA binary at
  all. MCP, export, and the prod-local identity path are different
  boots.
- Connections that have already closed by the time `lsof` runs.
  `lsof` is a snapshot. A short `fetch` during boot can come and
  go between samples. Packet capture closes that hole and opens
  the next one (root, privacy, and every other process on the
  machine).
- Attribution. `lsof` on the service pid is the only scope that
  stays honest. Observing the host, the process group, or the
  leased stack will see the shell, the gateway, and Bun itself.

**What it breaks.**

- Timing. A gate that races `lsof` against a live server will fail
  green or fail red depending on when the sample lands. This repo
  has already paid for assertions that are true of a stale artifact.
- IPv6. `localhost` resolving to `::1` while the allow-list names
  `127.0.0.1` is an ordinary Mac. `assert-loopback.ts` already
  enumerates non-loopback IPv4 only; an outbound dual that forgets
  `::1` will fire on every healthy boot.
- The gateway process's upstream, if the assertion is accidentally
  scoped to the stack rather than the service pid. Under
  `OMI_CHAT_MODEL=real` that upstream is the sanctioned chat
  provider. Under the canned gateway there is no upstream. A gate
  that is green on canned and red on real (or the reverse, if
  someone allow-lists `api.z.ai` "to make L3 pass") is a lie keyed
  on an env flag.
- Debugger / inspector sockets, the Bun control Unix socket, and
  macOS peer connections that are not HTTP. A first `lsof -iTCP`
  dump of a headed L3 will contain things nobody put in a design
  doc. Each one is a mute-or-hatch decision.

**Cost to build.** Larger than A, and it cannot live in L0. It needs
a booted process, so it is an L2-or-later assertion. `qa:contracts`
already runs `lint:closure`; it does not boot the headed stack.
Putting this in L0 would make L0 wait on a server.

**Cost to live with.** High until the false-positive set is named
and dated, the way Rule 16 and Rule 17 were. A connection observer
that fires on ordinary boots gets a hatch, then a broader hatch,
then it is a comment.

## Where the false positives come from

This is the part that decides whether the gate survives contact. A
gate that fires on legitimate traffic gets muted within a week, and
a muted gate is a lie in the repo. Rule 16's own header says the
same thing about a registry that tried to cover every port on day
one (`scripts/lint-import-graph.ts`).

The false positives that will actually show up, not a strawman:

1. **Loopback under four spellings.** `127.0.0.1`, `::1`,
   `localhost`, and a `URL` whose hostname is empty because someone
   passed a path. Chat, boot-acceptance, MCP tests, and the LAN
   negative probe all depend on at least one of these. An allow-list
   that names only `127.0.0.1` will fail a healthy IPv6 boot.
2. **In-process `app.fetch`.** Hono's `app.fetch(Request)` is not
   network. Tests use it with fictional hosts
   (`route-hardening.invalid`, `hidden-vs-absent.invalid`,
   `omi.local`). A wrap that keys on `Request.url` without asking
   "did this leave the process?" will fail the suite that currently
   proves the routes.
3. **Injected `fetch` in Chat tests.**
   `createGatewayChatGenerationSource({ fetch })` is how gateway
   tests stay hermetic. The injected function is not global `fetch`.
   A wrap that monkey-patches `globalThis.fetch` still has to leave
   this seam alone.
4. **The LAN negative probe.** `assert-loopback.ts` must be allowed
   to *attempt* non-loopback `fetch`es that are expected to fail. It
   is a separate process. Keep it that way.
5. **Firebase host sprawl, if v1 tries to name Google.**
   `securetoken.google.com` is the issuer string in
   `apps/service/auth/firebase-identity.ts`. It is not necessarily
   the host `firebase-admin` contacts. Admin SDK traffic, if it
   appears at all on `fetch`, may be `identitytoolkit.googleapis.com`,
   `www.googleapis.com`, `oauth2.googleapis.com`, or whatever that
   SDK version uses this month. A guessed Google list will be both
   incomplete (real calls denied → hatch) and overly broad
   (`*.google.com` → the fence is a comment). Do not pre-seed it.
   Measure, then add a row.
6. **The Auth emulator.** `FIREBASE_AUTH_EMULATOR_HOST` is a
   loopback host on the prod-local `--local-identity` path
   (`scripts/prod-local.ts`). It is not production Firebase. A CLOUD
   allow-list that names only Google hosts will break the one local
   identity path David already granted. A list that names the
   emulator host in deployed mode is the opposite defect. The wrap
   has to follow `runtime_mode`, not a single global list.
7. **Postgres on loopback.** `bun run prod-local` talks to the
   managed local PostgreSQL harness. That is TCP to a loopback port,
   not `fetch`. Candidate A v1 will not see it (correct). Candidate
   B will, and must allow that port without allowing every TCP peer.
8. **The headed shell and the gateway.** Candidate B scoped to
   "the machine" or "the leased stack" will see WKWebView → 5290,
   service → 8788, and (on real-model) gateway → `api.z.ai`. Only
   the middle hop is the service. The other two are not violations.
9. **iOS custom-scheme probe pages.**
   `frontend/shells/ios/surface/scheme/main-esm.ts` and
   `surface/loop/main-esm.ts` fetch `postman-echo.com`,
   `httpbingo.org`, `api.github.com`, `www.apple.com`, and
   `neverssl.com` as ATS/CORS probes. They are not Rule 18
   subjects. A tree-wide URL grep used as a gate will fire on them
   forever, or will grow a directory exemption that also hides a
   real leak. Do not use a tree-wide URL grep as this fence.
10. **Stale allow-list rows.** A host that used to be contacted and
    is not anymore is the Rule 16 stale-`composedIn` failure, ported
    here. A list nobody can delete from only grows. An unused row
    must fail, or the list will eventually permit everything.

The failure mode to optimize against is (10) plus (5): a list that
grows under mute pressure and never shrinks.

## Tests and QA loopback

Legitimate loopback traffic this fence must not fail:

| Path | Who fetches | Destination | Lane |
|---|---|---|---|
| Headed local service | macOS/iOS shell, `boot-acceptance.ts`, humans | `127.0.0.1:4851` | L2/L3/L4 |
| Chat generation | LOCAL service, via `createGatewayChatGenerationSource` | `OMI_LLM_GATEWAY_URL` (canned 8788 or real-model 8791, both loopback) | L3 default canned; real is opt-in |
| Gateway `/ready` probe | LOCAL service, `probeGatewayEngineIdentity` | same gateway origin | boot |
| In-process route tests | `app.fetch` | fictional hosts, no socket | `bun test` / L2 |
| Spawned-server tests | global `fetch` | `127.0.0.1:<ephemeral>` | `bun test` / L2 |
| LAN negative probe | `assert-loopback.ts` (separate process) | non-loopback IPv4, expected to fail | boot-acceptance |
| prod-local HTTP | clients | `127.0.0.1:4851` through the CLOUD kernel | manual / `bun run prod-local` |
| prod-local Postgres | CLOUD process, TCP | managed local Postgres | `test:postgres:*` |
| Auth emulator | CLOUD process, only with `--local-identity` | `FIREBASE_AUTH_EMULATOR_HOST` | opt-in |

v1 of candidate A, installed only at the four entrypoints, with
loopback as a first-class allow, leaves `bun test` alone. Boot acceptance
starts real loopback HTTP through those entrypoints, so the wrap is live
at the first real network contact.

`OMI_LLM_GATEWAY_URL` on the LOCAL process should be required to
resolve to a loopback host, not merely to "whatever is in the env".
That is stricter than today's parser (`gatewayEndpoint` already
rejects credentials, query, and hash; it does not require
loopback). The follow-up lane should treat a non-loopback gateway
URL as a fence failure, because that is how the local service would
silently become a model client without linking `drivers/model/*`.

The canned gateway and the real-model proxy are out of v1's
process-scope. Their upstream is the sanctioned chat-model leak,
owned by that process, refused from ever being `api.omi.me`
(`integration/local-model-gateway.mjs`). Do not fold that check into
the service wrap.

## Keeping the allow-list honest

Copy the discipline Rule 16 and Rule 17 already paid for, do not
invent a third hatch primitive.

- **David-only rows**, same as Rule 18's entrypoint and forbid
  lists (`trace-value-imports.ts`). If a boot fails, fix the call,
  never the list, unless David adds the host.
- **No wildcards.** `*.google.com`, `*.googleapis.com`, and "any
  private RFC1918" are how a list starts permitting everything.
  Loopback is a named class (`127.0.0.1`, `::1`, `localhost`), not
  a wildcard.
- **Opt-in, measured.** Start with loopback only. A non-loopback
  host is added when a real, sanctioned call is denied, with the
  denying URL and the process (LOCAL vs CLOUD, `runtime_mode`) in
  the row. Do not pre-seed Firebase hosts from memory.
- **Stale rows fail.** A host that was not contacted by the
  process that claims it, across the lane that exercises that
  process, is a stale row. Same shape as a `PORT_REGISTRY`
  `composedIn` path that no longer constructs the port. Without
  this, the list only grows.
- **Keyed by (process group, runtime_mode, host), not by file.**
  LOCAL deployed-QA, CLOUD deployed, and CLOUD `local_test` /
  emulator are three different legitimate sets. One table that
  unions them is how the emulator host leaks into deployed mode
  and how a Google host becomes required on the SQLite QA binary,
  which does not import Firebase identity.
- **No comment-marker hatch.** Rule 16 and Rule 17 already
  demonstrated that `// something-ok(...)` is a forgeable switch
  on the mechanism whose job is to turn the fence off. A host
  exemption is a row in the one file everybody already watches.
- **Do not use a tree-wide `https://` grep as the fence.** It will
  fire on tests, docs, iOS probes, and `api.omi.me` mentions whose
  whole job is to refuse that host. Those greps are useful audits;
  they are not a ratchet.

The unused-row check is the piece that will feel bureaucratic and
is the piece that keeps the list from becoming the lie. Budget it.

## Recommendation

**Build candidate A first, v1 = wrap `fetch` at the four Rule 18
entrypoints, allow loopback only, require `OMI_LLM_GATEWAY_URL` on
LOCAL to be loopback, David-only host table empty of non-loopback
rows, stale-row check from day one.**

Reason: the remaining hole is exactly an inline `fetch` in an
allowed file, plus a gateway URL that is already a string the
parser does not constrain to loopback. That is a call-layer
question. Candidate B answers a different question (SDK and TCP
peers) with a false-positive surface this repo has already shown
it will mute: snapshots, IPv6, debugger sockets, the gateway
upstream, the headed shell. B is a backstop, not a first fence.

Name what v1 does not cover, in the wrap's own comment, the way
this document names what Rule 18 does not cover:

- `firebase-admin` HTTPS
- `postgres.js` TCP
- `node:https` / `Bun.connect` / subprocesses
- the gateway process's model-provider upstream
- the headed shell

**Do not build candidate B in the same lane as A.** Land A. Let it
sit through L2 without a hatch. If it needs a hatch, A is wrong and
B will not save it. After A is boring, a second lane can add an
`lsof`-style established-peer assertion on the **service pid
only**, as the SDK/TCP backstop, with a measured peer dump from a
canned L2 attached to the proposal for that lane. Not before.

**Do not expand Rule 18 to grep URLs.** The tracer's job is the
import graph. Mixing a second question into `lint:closure` would
make a red on a forbidden module indistinguishable from a red on a
host, and would teach people to treat both as "the import lint
being noisy."

## Follow-up lane — starting points

When David rules, the implementing lane should begin here:

1. Read this file and [`docs/architecture.md`](architecture.md)
   ("Two sanctioned network destinations"). Do not re-derive the
   gap. Do not change Rule 18's forbid lists.
2. Prove, on the current four closures, that no module `fetch`es at
   import time before an entrypoint-local wrap can be installed.
   The first-import module is the whole mechanism; if it is loaded
   second, it is decoration.
3. Install the wrap so that `options.fetch ?? fetch` in
   `apps/service/chat/generation-source.ts` and
   `probeGatewayEngineIdentity` in
   `apps/service/chat/gateway-engine-identity.ts` see it on the
   LOCAL boot path. Red-proof: an inline
   `fetch("https://example.invalid")` in `dev-server.ts` (or a
   helper it value-imports) must fail the wrap; `lint:closure` must
   stay green on that same tree, or the two fences have been
   collapsed.
4. Require `OMI_LLM_GATEWAY_URL` to be loopback at the same wrap
   (or at `gatewayEndpoint`). Red-proof: pointing it at
   `https://api.z.ai` must fail the LOCAL process without linking
   `drivers/model/glm`.
5. Do not preload the wrap into `bun test`. L2 is the first lane
   that boots the real entrypoints; that is where the wrap first
   has to be green on legitimate loopback.
6. Leave `assert-loopback.ts`, `integration/local-model-gateway.mjs`,
   and `frontend/shells/ios/surface/` out of the wrap. They are
   different processes with different jobs.
7. Host-table edits are David-only. The implementing lane does not
   add `api.z.ai` or a Google host to make a test pass.

Out of scope for that lane, unless David says so in those words:
wrapping `node:https`, observing `lsof` peers, changing Rule 18's
lists, and any request to `https://api.omi.me`.
