# omi — Even Realities G2 plugin

The omi app for Even Hub. A five-row menu on the glasses, backed by the local
omi bridge in [`../bridge`](../bridge) over a WebSocket. Scroll moves the
selection, tap opens, double-tap goes back — and exits from the menu.

```
+--------------------------------------------------+
| > Ask Omi                                        |
|   Memories                                       |
|   Action items                                   |
|   Today                                          |
|   Capture: off                                   |
|--------------------------------------------------|
| scroll move | tap open | double-tap exit         |
+--------------------------------------------------+
```

| Row | What it does |
|---|---|
| **Ask Omi** | Asks a question and streams the answer in, paging at ~380 chars. Tap again for the next question. |
| **Memories** | Last 20 memories, paginated. |
| **Action items** | Open and completed items, `[ ]` / `[x]`. |
| **Today** | Today's summary. |
| **Capture: on/off** | Toggles the glasses microphone (`audioControl`). |

The bottom strip is always present: it shows the connection state, the page
position, or the most recent `push` banner from the bridge.

## Run it

```bash
npm install
npm run dev          # Vite on :5273, bound to the LAN
```

Port **5273**, not Vite's default 5173 — the sibling `integrations/evenhub-g2`
app claims that one, and `strictPort` is on so running both would otherwise fail.

**In the simulator** (no hardware needed):

```bash
npm run simulator    # separate terminal
```

**On real glasses** — phone and laptop on the same Wi-Fi, developer mode enabled
in the Even Realities companion app:

```bash
npm run qr           # auto-detects the LAN IP; scan from the phone app
```

Edits hot-reload on the glasses without rescanning.

**Package for submission:**

```bash
npm run build && npx evenhub pack app.json dist
```

## Pointing it at a bridge

The default is `ws://127.0.0.1:8788/app`, which matches
[`../bridge/run.sh`](../bridge/run.sh). That only resolves for the desktop
simulator — the glasses render through the *phone's* WebView, so on real
hardware you must give it a reachable host:

```
http://<laptop-ip>:5273/?bridge=ws://<laptop-ip>:8788/app
```

Resolution order is query param → `VITE_OMI_BRIDGE_URL` at build time → the
constant in `src/config.ts`.

If the bridge is not there, the app says `bridge offline - retrying …` in the
status strip and reconnects with backoff (500 ms → 8 s). It never blocks on the
socket, so a missing bridge is a visible state, not a hang.

### Protocol

Sent: `chat` · `memories` · `action_items` · `today`.
Received: `chat_delta` · `chat_done` · `memories` · `action_items` · `today` ·
`push`. Anything else — the bridge's `hello`, `transcript`, `pong` — is ignored
with a debug log, so a bridge that grows new message types does not break an
older build of the app.

## Verify

Two suites. Run both.

```bash
npm test             # hermetic unit tests — no GUI, no network, CI-safe
npm run dev          # must be running for the next one
npm run verify       # end-to-end against the simulator
```

`npm test` covers pagination, the wire format, and background-state snapshotting
by importing `src/*.ts` directly through Node's TypeScript stripping. No build
step, no simulator.

`scripts/verify-simulator.mjs` starts its own mock bridge
(`scripts/mock-bridge.mjs`, a dependency-free RFC 6455 server serving fixed
fixtures) plus the simulator, then drives the automation HTTP API and asserts
the app actually works: the bridge connects, the home list renders non-blank at
576x288, scroll moves the highlight, every row opens and loads, a chat answer
streams in and repaints **in place** rather than by rebuilding the page, a
multi-page answer pages with scroll, a server push renders as a banner, losing
the bridge shows as offline and retries, the app never reloaded mid-run, and
nothing threw. It decodes the PNG framebuffer in pure Node, so there is no
image-library dependency.

It refuses to start if the automation port or the bridge port is already taken —
a leftover process would answer every request and produce a green run against a
stale instance — and it kills the process *group*, since the simulator launcher
execs a platform binary that survives killing the Node launcher.

It needs a GUI (the simulator opens a window), so it is a **local** check and is
deliberately not wired into CI. `npm test` is the CI-safe half.

## Notes for anyone extending this

- **Touch input arrives on three different channels.** Tap and double-tap come
  as `sysEvent`, scroll over a text container comes as `textEvent`, and a list
  container reports as `listEvent`. `src/main.ts` reads whichever channel the
  event carries. Verified against SDK 0.0.12 in the simulator:

  | input | delivered as |
  |---|---|
  | `click` on a text container | `sysEvent: {eventSource: 1}` — `eventType` absent |
  | `click` on a list container | `listEvent: {containerID, containerName, currentSelectItemIndex?}` |
  | `double_click` | `sysEvent: {eventType: 3}` |
  | `up` / `down` over a text container | `textEvent: {containerID, eventType: 1 / 2}` |
  | `up` / `down` over a list container | **nothing** |

- **Two absent-means-default traps**, both from proto3 dropping zero values:
  an absent `eventType` is `CLICK_EVENT`, and an absent `currentSelectItemIndex`
  is **row 0**. The second one matters because scrolling a list emits no event
  at all — the OS moves its own highlight and only reports the row on the click
  that follows. Treating the missing index as "unknown" strands the app on
  whichever row it last saw, which is exactly the bug the verify harness caught.

- **All SDK calls are serialized** through one FIFO in `src/display.ts`, each
  racing a 5 s timeout. Concurrent bridge calls can crash the connection, and a
  flaky BLE hop otherwise hangs for ~30 s.

- **Streaming uses `textContainerUpgrade`, never `rebuildPageContainer`.**
  Upgrades are flicker-free and in place, but the container ID *and* name must
  both match or the host drops the update with no error. Rebuilds are reserved
  for real layout changes: entering/leaving a view, and relabelling the Capture
  row (list items cannot be updated in place). Chat deltas are coalesced behind
  a 150 ms dirty-flag loop rather than queueing one upgrade per delta.

- **`createStartUpPageContainer` is called exactly once**, at boot, with the
  home layout. A WebView reload calls it again and the host returns `invalid`
  because the containers already exist; the app logs that at `warn` and keeps
  going, since updates still land. `oversize` and `outOfMemory` are still real
  errors. The simulator does reload itself once shortly after start-up, so the
  verify harness waits for that to settle before it touches anything.

- **`setBackgroundState` / `onBackgroundRestore` are implemented locally**, in
  `src/background-state.ts`. The Even Hub docs describe them as SDK exports, but
  `@evenrealities/even_hub_sdk@0.0.12` — the latest published version — does not
  ship them: the symbols are absent from both `dist/index.d.ts` and
  `dist/index.js`. The local module implements the host's documented
  `window.__getStateSnapshot()` / `window.__restoreState()` hooks, so call sites
  read exactly as they will once the SDK ships them and the import becomes a
  one-line swap.

- **There is no keyboard and no on-device ASR**, and the bridge protocol carries
  text rather than audio, so "Ask Omi" cycles a fixed ring of prompts rather
  than dictating a question. Wiring the glasses mic to speech-to-text needs an
  audio message type the contract does not define yet.

- **`server.host: true` in `vite.config.ts` is required.** Vite binds to
  localhost by default and the phone would get connection refused. `strictPort`
  is on so the dev server fails loudly rather than drifting to :5274 and leaving
  a QR code pointing at a dead port.

- **TypeScript is pinned to ^5.** `@evenrealities/evenhub-cli` declares a
  `typescript@^5` peer; current `create-vite` scaffolds TS 6.

- **The simulator needs its platform binary.** `@evenrealities/evenhub-simulator`
  shells out to `@evenrealities/sim-<platform>-<arch>`, which is not pulled in
  automatically — hence the explicit `@evenrealities/sim-darwin-arm64`
  devDependency. Add the matching package for other platforms.

- The DOM is not the display. `index.html` only hosts the script; everything the
  user sees is drawn through the SDK bridge on the 576x288 canvas.
