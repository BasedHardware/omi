# Native iOS semantic fixture evidence

`capture-native-semantic-evidence.mjs` is an offline fixture producer. It
builds a pinned `SURFACE_QUERY` into the Flutter app, runs the dedicated
`RunnerUITests` target on one iOS Simulator, exports the single retained JSON
attachment from the `xcresult`, and writes one canonical matrix artifact per
typed coordinate (`omi.polish.ax/v1` or `omi.polish.keyboard/v1`). It never
accepts a backend URL/token and passes a small allowlisted environment to child
processes.

The producer requires a manifest with full core/platform SHAs. `--source-root`
allows the tool checkout and the product-source checkout to be separate (the
default source root is the tool's core worktree) and verifies the manifest's
core SHA against that exact source checkout.
Matrix manifests use `schema: omi.polish.matrix-coordinate/v1`, an exact
`kind` (`ax_snapshot` or `keyboard_trace`), and the corresponding accessibility
mode (`ax_snapshot` uses one of the six explicit AX modes; `keyboard_trace`
uses `keyboard`). AX coordinates use the regular logical viewport. The current
fixture does not expose a domain landmark or a real keyboard transition, so a
matrix run fails closed rather than emitting a misleading row. The checked-in
`native-semantic-chat-ready.json` is deliberately marked
`omi.native-ios-semantic-supplementary/v1` and uses the logical compact
viewport 402x874@3; its application/WebView result cannot close matrix rows.
The optional `--platform-root` independently checks the pinned platform SHA;
otherwise the platform SHA remains an externally supplied provenance claim for
the coordinator to verify.

With Flutter 3.44.5 and a booted iPhone 17 Pro simulator:

```sh
SURFACES_DIST=/absolute/path/to/core/packages/surfaces/dist \
FLUTTER_BIN=/Users/dazheng/.local/share/mise/installs/flutter/3.44.5/bin/flutter \
NODE_BIN=/Users/dazheng/.local/share/mise/installs/node/22.23.2/bin/node \
node core/shells/ios/tools/capture-native-semantic-evidence.mjs \
  --manifest core/shells/ios/fixtures/native-semantic-chat-ready.json \
  --source-root /absolute/path/to/pinned-core-source \
  --platform-root /absolute/path/to/omi-platform \
  --output-dir /absolute/path/to/core/.build/native-ios-semantic/chat-ready
```

For a matrix coordinate, the native run is only the preparation stage; its
`native-preparation-receipt.json` is deliberately not a ledger
`command_receipt`. Once a
prepared `matrix-ax.json` or `matrix-keyboard.json` has passed the marker checks,
run the same wrapper in replay mode into a fresh output path:

```sh
node core/shells/ios/tools/capture-native-semantic-evidence.mjs \
  --manifest core/shells/ios/fixtures/<matrix-coordinate>.json \
  --replay-input core/.build/native-ios-semantic/<run>/matrix-ax.json \
  --replay-output core/.build/native-ios-semantic/<run>/gate/matrix-ax.json
```

Replay copies only the prepared regular file, binds its SHA in a verifier-shaped
`input_set`, and writes a one-member `batch_id`/`command_receipt` plus coverage
document. The command receipt's stdout hash is tied to the deterministic replay
line; deleting the output and rerunning the recorded argv is the required
causal check. The current supplementary fixture never reaches this path.

The UI test emits only allowlisted role/name pairs and action outcomes. A
keyboard artifact is emitted only when a real text-field focus, key action,
target transition, and Escape restoration are observed; a command/escape
attempt alone is never accepted. When the fixture exposes only the WebView
host, the truthful supplementary result is a native application/WebView
snapshot and a WebView tap, not fabricated Chat controls.
