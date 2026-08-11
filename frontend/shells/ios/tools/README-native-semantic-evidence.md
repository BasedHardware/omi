# Native iOS semantic fixture evidence

`capture-native-semantic-evidence.mjs` is an offline fixture producer. It
builds a pinned `SURFACE_QUERY` into the Flutter app, runs the dedicated
`RunnerUITests` target on one iOS Simulator, exports the single retained JSON
attachment from the `xcresult`, and writes canonical `omi.polish.ax/v1`,
`omi.polish.keyboard/v1`, and receipt artifacts. It never accepts a backend
URL/token and passes a small allowlisted environment to child processes.

The producer requires a manifest with full core/platform SHAs. `--source-root`
allows the tool checkout and the product-source checkout to be separate (the
default source root is the tool's core worktree) and verifies the manifest's
core SHA against that exact source checkout.
The manifest also requires
`capture_class: native_fixture`, `source_tier: native_shell`, and
`accessibility: none` (the current UI test does not enable VoiceOver or other
system modes). The optional `--platform-root` independently checks the pinned
platform SHA; otherwise the platform SHA remains an externally supplied
provenance claim for the coordinator to verify.

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

The UI test emits only allowlisted role/name pairs and action outcomes. It may
record a real `typeKey` command/escape probe when a native text field exposes a
visible keyboard; it does not claim a product shortcut or read element values.
When the fixture exposes only the WebView host, the truthful result is a native
application/WebView snapshot and a WebView tap, not fabricated Chat controls.
