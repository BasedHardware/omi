# Native runtime matrix evidence

`capture-native-runtime.mjs` produces one `runtime_trace` coordinate from an
actual native shell. It is intentionally not a screenshot or AX producer.

## Contract

The manifest must be an exact `omi.polish.matrix-coordinate/v1` object with
`kind=runtime_trace`, `capture_class=native_fixture`, `source_tier=native_shell`,
`width=regular`, an applicable lifecycle state, and full `core`/`platform` SHAs.
The producer independently resolves both worktrees before a live capture.

macOS launches `shells/macos/scripts/dev-capture-macos.sh --fixture` with an
allowlisted environment and an `OMI_PROBE_JS` expression. The result is read
from the real headless WKWebView's `PROBE_JS` line; an absent/malformed marker,
wrong state, or unallowlisted computed style fails closed. iOS runs the
`RunnerUITests/NativeRuntimeEvidenceUITests/testNativeRuntimeEvidence` test on
the real fixture WebView. The opt-in `OMI_POLISH_RUNTIME_PROBE=1` hook in
`OmiUiWebView` posts only redacted lifecycle/computed-style records to a native
accessibility identifier; normal app launches do not install that handler.

The output `runtime.json` is exact `omi.polish.runtime/v1` metadata plus typed
events. To prepare gate input, replay that file into a fresh output:

```sh
node core/shells/tools/capture-native-runtime.mjs \
  --manifest core/shells/.../coordinate.json \
  --replay-input core/.build/polish-native-runtime/<run>/runtime.json \
  --replay-output core/.build/polish-native-runtime/<run>/gate/runtime.json \
  --output-dir core/.build/polish-native-runtime/<run>/gate
```

The replay writes the immutable input set, batch member, command receipt, and
one-coordinate coverage record. Its recorded argv includes
`--emit-gate-records false`, so a verifier rerun creates only the declared
artifact and cannot close a row from a pre-existing no-op file.

The iOS path remains honestly red when the managed simulator, app bundle, or
typed host marker is unavailable; no browser preview or guessed state may be
relabeled as native evidence.
