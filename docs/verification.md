# Verification: what a lane is entitled to claim

The rule, encoded in `integration/lanes.mjs:21-24`:

> An agent may only claim something works at the lane it actually ran.

L1 green means the unit holds. It does not mean the app works. The receipt
records which lane it was so the claim cannot quietly inflate later.

Run a lane with `node integration/lanes.mjs L0` (or `L1`, `L2`, `L3`,
`L4`). The runner invents no checks. Every command is one you could type
yourself (`lanes.mjs:8-10`). Time budgets are printed, never enforced
(`lanes.mjs:457-459`).

Frontend and backend now live in this repository
(`integration/lib/provenance.mjs:98-103`). `OMI_CORE_ROOT` and
`OMI_PLATFORM_ROOT`, if set, must name the same checkout.

Related: [`docs/architecture.md`](architecture.md),
[`docs/chat-provenance.md`](chat-provenance.md),
[`docs/running-locally.md`](running-locally.md). How to add a control step
is in `integration/control-acceptance/README.md` (read that file before
trusting its hold-status sentences; the runner in `lanes.mjs` is the
authority for which steps are gates).

## L0 — reflex, static only

Entitled to claim: the import fence, contract drift, wire conformance, and
codegen drift are green. Not entitled to claim a test passed, a server
booted, or the app rendered.

`lanes.mjs:75-96`. No build, no server, no app (`lanes.mjs:13-14`). Steps:

1. `bun run lint:imports` (Rule 16 port registry and Rule 17 wire-path
   fence, not Rule 18)
2. `bun test` on the two contract-drift files
3. `node scripts/check-wire-conformance.mjs` under `frontend/`
4. `pnpm codegen:check` under `frontend/`

`bun run qa:contracts` is not an L0 check. It runs the whole backend suite
after verifying the vendored tarball (`lanes.mjs:80-89`). That belongs in
L2.

## L1 — unit, frontend

Entitled to claim: `pnpm verify` is green — build, unit tests, and the
frontend static checks. Not entitled to claim the app works, or that a
loopback service served a request.

`lanes.mjs:98-105`. One step: `pnpm verify` in `frontend/`. That is the
Definition of Done named in `frontend/AGENTS.md`.

## L2 — hermetic integration

Entitled to claim: the backend suite, `integration/`, and cross-side wire
agreement hold on real loopback HTTP, on this lane's own ports, with no
shell and no simulator. Safe to run alongside a live stack
(`lanes.mjs:16-18, 107-109`).

Not entitled to claim a human clicked a control, or that WKWebView rendered
a transcript.

Preflight (`lanes.mjs:120-129`): `adapters-platform` must already be built,
and the surfaces dist stamp must agree with the working tree. A stale dist
makes the cross-side test exercise yesterday's client and pass.

Steps (`lanes.mjs:150-174`):

1. `bun run qa:contracts` (includes `bun test` and `lint:imports`)
2. `bun test integration/`
3. `node --test integration/cross-side/*.test.mjs` (every file in that
   directory)
4. A listed set of hermetic `integration/lib` and launcher-structure tests,
   including receipts concurrency

## L3 — the whole stack, then the sibling that clicks

Entitled to claim: **the app works**, for the macOS shell, on the controls
this lane actually clicked. Headless and assert-based by default
(`lanes.mjs:187-190`). A traffic count is not this claim.

Not entitled to claim the listen→memory→chat chain (that is L4). Not
entitled to claim iOS received the same click-through: the second step is
macOS-only. iOS uses the same runner with `--ios`; that command is not an
L3 step.

Steps (`lanes.mjs:191-222`):

1. `integration/dev-stack.sh --assert --lease` — boots a leased stack,
   drives both native shells for the evidence matrix
2. `node integration/control-acceptance/run.mjs` — clicks Home, Chat,
   Listen, Rewind, and every chrome route in the built macOS shell

The second step is a gate (`lanes.mjs:196-221`). Default Chat is the canned
gateway.

## L4 — journey, listen to chat-memory

Entitled to claim: one rendered-layer chain happened in the same shell, on
the same leased stack, with no hop stubbed (`lanes.mjs:225-228`). Too slow
to fold into L3; do not add it there.

Not entitled to claim a per-domain token from L3. The four earlier hops can
all pass while retrieval fails; that is why this tier exists
(`lanes.mjs:264-265`).

One step: `node integration/control-acceptance/run.mjs --journey`
(`lanes.mjs:270-275`). Canned gateway by default. `--seam-break` leaves
listen/memory/chat endpoints healthy and drops the identified memory from
the served request; the journey must then print
`CONTROL chat.memory=memory-not-retrieved` while the earlier hops still
hold.

## Control-acceptance: outcome tokens

Pass tokens are outcomes, not plumbing. `reached-os` is not a pass. The
vocabulary lives in `integration/control-acceptance/verdict.mjs`. Slugs are
frozen; add a row, never rename one (`verdict.mjs:15, 63-65`).

Control-walk slugs (`verdict.mjs:16-32`) and their pass tokens
(`verdict.mjs:68-88`):

| slug | pass token | what it means in this tree |
|---|---|---|
| `home` | `ready` | Home rendered without the saved-data failure notice |
| `chat` | `streamed-and-persisted` | assistant streamed and persisted, **and** the three provenance witnesses agree ([`docs/chat-provenance.md`](chat-provenance.md)) |
| `mic` | `transcript-rendered` | published segment count > 0, transcript attribute non-empty, and visible `.listen-transcript-row` text non-empty (`verdict.mjs:150-168`) |
| `screen` | `frame-rendered` | a selected timeline frame renders a PNG `<img>` with nonzero `naturalWidth`; `.screen-frame-unavailable` is a fail (`verdict.mjs:179-192`) |
| `nav.*` | `rendered` | each chrome route rendered |

Journey slugs are a separate inventory (`verdict.mjs:40-46`) so a full
control walk cannot pass a hop it never drove:

| slug | pass token | what it means |
|---|---|---|
| `mic` | `transcript-rendered` | same as the control walk |
| `conversation` | `row-rendered` | Conversations lists a `data-conversation-id` absent before listen (`verdict.mjs:239-247`) |
| `memory` | `card-rendered` | Memories shows a new `data-proposition-id` whose `.proposition-text` carries a listen needle from this run (`verdict.mjs:258-274`) |
| `home.memory` | `row-rendered` | Home's spine contains that card's rendered text (`verdict.mjs:283-292`) |
| `chat.memory` | `retrieved-and-streamed` | chat streamed and persisted, provenance agrees, **and** the served gateway request contains the `memory_projection` payload of the Memories record id (`verdict.mjs:352-366`) |

Anything else on a slug is a fail, including `missing-step`,
`empty-transcript`, `frame-unavailable`, `bridge-unreachable`,
`provenance-mismatch`, `canned-answer`, `memory-not-retrieved`.
`skipped-already-granted` is not a skip; it fails (`verdict.mjs:59-61`).

Overall (`verdict.mjs:471-487`):

```text
CONTROL-ACCEPTANCE status=PASS|FAIL passed=N failed=N skipped=N
```

`status=PASS` only when every step in the inventory passed or was a
legitimate skip.

### Why `skipped-tcc-denied` is the only sanctioned skip

`SKIP_VERDICTS` is a closed list (`verdict.mjs:62-65`):
`skipped-tcc-denied` and `skipped-not-requested`. Prefix-matching
`skipped-*` is how a real failure was laundered into a pass.

- `skipped-tcc-denied` is host state this harness does not own: macOS TCC
  already decided the microphone (or screen) is denied. The harness cannot
  click a system prompt. It prints the skip and does **not** count it as a
  pass (`verdict.mjs:7-9, 453-457`). That is the only legitimate skip of a
  control the run actually requested.
- `skipped-not-requested` is a mode artifact: `--screen-proof` does not
  drive Chat, so those slugs are recorded as not requested. They are skips,
  not passes. A dead screen still fails that run.

A journey run sets `allowSkip: false` (`run.mjs:312, 345, 360`). A skip,
including `skipped-tcc-denied`, fails L4: the chain did not happen.

Do not treat the older `ACCEPTANCE … servedCount=… status=PASS` line as a
control result. That is `dev-app.sh --accept`, a different mode.

## What the five journey hops prove that per-domain tokens do not

L3 can print `mic=transcript-rendered` and `chat=streamed-and-persisted` as
two independent clicks. That does not prove the transcript became a
conversation, that the conversation became a memory, that Home showed that
memory, or that Chat retrieval was joined by that memory's id.

L4 drives that chain in one shell (`lanes.mjs:228`). Retrieval is a join on
the record written earlier in the same run, by id, against the served
gateway request — not a search of the assistant's prose
(`verdict.mjs:341-346`). The `--seam-break` red-proof keeps every endpoint
healthy and removes only that record from the served set
(`verdict.mjs:348-350`). The four per-domain hops still passing while the
chain fails is the argument for the tier.

## Port and origin leases

David's long-lived app and a verification run are different products and
use different ports. Do not unify them because they look similar
(`apps/service/net/port-lease.ts:43-46`,
`integration/lib/stack-port-lease.ts:15-19`).

Pinned (the headed app, `bun run app`, `dev-stack.sh --up` without
`--lease`):

| Role | Port |
|---|---|
| app-facing service | 4851 |
| canned Chat gateway | 8788 |
| real-model Chat gateway | 8791 |
| macOS surface origin | 5290 |

Verification (`--lease`, L3, L4, control-acceptance full/journey) acquires
exclusive locks in bounded ranges (`port-lease.ts:27-41, 61-66`):

| Role | Range |
|---|---|
| app-facing | 14851–14870 |
| canned gateway | 18788–18807 |
| real gateway | 18811–18830 |
| macOS surface | 15290–15309 |

5290 is the long-lived origin: IndexedDB persists across relaunch. A
verification run leases 15290–15309 so it gets a clean origin. If it cannot
acquire a surface port, it refuses loudly and never falls back to 5290
(`stack-port-lease.ts:17-19`, `run.mjs:227-233`).

`--up` without `--lease` refuses if 4851 or the chosen gateway port is
already occupied; it will not kill the listener or drift ports
(`integration/dev-stack.sh:330-346`). Occupied 5290 is refused on the
assert path (`dev-stack.sh:348-357`), not on `--up`. `bun run app` stays
on 5290 (`integration/dev-app.sh:17-20, 151`).

Control-acceptance full and journey runs always boot `--up --lease`
(`run.mjs:174-180`), so they can coexist with David's app on 4851/5290.
`--screen-proof` is the exception: it attaches to the long-lived 4851
service and the 5290 origin (`run.mjs:150-154, 192-195`).

### What still cannot run twice at once

- Two unleased stacks. 4851, 8788 (or 8791), and 5290 are exclusive.
- Two headed apps on 5290. The origin is the persistence key.
- Two holders of the same leased port. The next acquire skips a live
  listener; it never evicts (`port-lease.ts:18-21, 229-231`). Exhausting a
  range is a refusal, not a fallback (`port-lease.ts:281-287`).
- `bun run prod-local` also wants 4851. It is the hosted kernel, not a
  second QA server; see [`docs/architecture.md`](architecture.md).
- Two processes in one range role after the twenty ports are taken.
- Two L3 iOS runs after four simulator leases are taken. The cap is
  `SIMULATOR_LEASE_MAX_CONCURRENT = 4`
  (`apps/service/net/simulator-lease.ts`). Exhausting it is a refusal that
  names the live holders, never a 124 timeout.

iOS origin is a frozen custom scheme
(`frontend/shells/ios/scripts/dev-run-ios.sh:18-20`), so it does not use
the 5290/15290 port lease. The device is leased the same way ports are:
a lock file plus a live-holder check, keyed by UDID
(`simulator-lease.ts`). `lanes.mjs` acquires one for L3 and passes
`--device <udid>` into `dev-stack.sh`. A booted simulator with no live
lease is treated as someone else's and is never shut down, erased, or
stolen. If no free shutdown device exists, the harness boots one, up to
the cap of 4.
