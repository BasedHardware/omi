# macOS semantic evidence probe

`native-semantic-evidence.swift` is a headed-shell observation helper. It reads
only bounded, allowlisted AX role/name tokens and can post an explicitly opted-in
CoreGraphics key sequence; it does not take screenshots or inspect page
JavaScript. Generic runs are always `supplementary_observation`.

Compile it on macOS with:

```sh
swiftc -O -framework AppKit -framework ApplicationServices -framework CoreGraphics \
  -o /tmp/omi-native-semantic-evidence native-semantic-evidence.swift
```

Matrix evidence must be run through `native-semantic-evidence-batch.mjs` with an
exact `omi.polish.matrix-manifest/v1` coordinate. The coordinator prepares and
hashes an immutable input set, writes verifier-shaped AX/keyboard members and a
receipt, and rejects unbound PIDs, bundles, source SHAs, landmarks, or keyboard
transitions. Keyboard coverage is accepted only when every target transition is
observed and Escape restores the bound focus identity.

The coordinator reports `blocked_gui_locked` (exit 3) when `lsappinfo front` is
`loginwindow`; this is an honest red result, not a fixture or browser substitute.
