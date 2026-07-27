# Omi G2 First App

The Even Hub [first-app quickstart](https://hub.evenrealities.com/docs/get-started/quickstart/first-app)
for Even Realities G2 smart glasses: one full-canvas text container that counts
taps and exits on a double-tap.

```
Hello from G2!

Tap to count: 0
Double-tap to exit
```

## Run it

```bash
npm install
npm run dev          # Vite on :5173, bound to the LAN
```

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

## Verify

```bash
npm run dev          # must be running first
npm run verify
```

`scripts/verify-simulator.mjs` drives the simulator's automation HTTP API and
asserts the app actually works: the bridge connects, the start-up container is
created, the framebuffer is non-blank at 576x288, two taps advance the counter
to 2, a double-tap requests the exit dialog, and nothing throws. It decodes the
PNG framebuffer in pure Node, so there is no image-library dependency.

It needs a GUI (the simulator opens a window), so it is a **local** check and is
deliberately not wired into CI.

## Notes for anyone extending this

- **Touch input arrives on two different channels.** The simulator delivers tap
  and double-tap as a `sysEvent`, and only scroll as a `textEvent`. The quickstart
  code in the docs reads `event.textEvent` only, so taps never reach the handler.
  `src/main.ts` reads whichever channel the event carries, which works in both
  places. Verified against SDK 0.0.12:

  | input | delivered as |
  |---|---|
  | `click` | `sysEvent: {eventSource: 1}` — `eventType` absent |
  | `double_click` | `sysEvent: {eventType: 3}` |
  | `up` / `down` | `textEvent: {containerID: 1, eventType: 1 / 2}` |

  An absent `eventType` means a plain tap; every other event type is explicit.

- **`server.host: true` in `vite.config.ts` is required.** Vite binds to
  localhost by default and the phone would get connection refused. `strictPort`
  is on so the dev server fails loudly rather than drifting to :5174 and leaving
  a QR code pointing at a dead port.

- **TypeScript is pinned to ^5.** `@evenrealities/evenhub-cli` declares a
  `typescript@^5` peer; current `create-vite` scaffolds TS 6.

- **The simulator needs its platform binary.** `@evenrealities/evenhub-simulator`
  shells out to `@evenrealities/sim-<platform>-<arch>`, which is not pulled in
  automatically — hence the explicit `@evenrealities/sim-darwin-arm64` devDependency.
  Add the matching package for other platforms.

- **Reloading an already-running page logs `createStartUpPageContainer failed: 1`**
  (`invalid`) because the container already exists. The app keeps working — updates
  still target the existing container. A fresh load is clean.

- The DOM is not the display. `index.html` only hosts the script; everything the
  user sees is drawn through the SDK bridge on the 576x288 canvas.
