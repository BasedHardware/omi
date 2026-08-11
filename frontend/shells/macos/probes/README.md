# macOS semantic evidence probe

`native-semantic-evidence.swift` observes a scratch shell without activating it
for AX snapshots. It reads only bounded, allowlisted AX role/name tokens and can
post an explicitly opted-in CoreGraphics key sequence; it does not take
screenshots or inspect page JavaScript. Generic runs are always
`supplementary_observation`.

Use the shell's default off-screen accessory mode for screenshots, runtime
probes, and AX snapshots. For keyboard traces, launch the scratch shell with
`OMI_SEMANTIC_WINDOW=1` instead of `OMI_HEADED=1`. That mode orders a small
accessory window behind the user's windows without activating it. The probe
temporarily activates the target for the bounded key sequence, then hides the
scratch window and restores the app that was previously frontmost before it
emits evidence. `OMI_HEADED=1` remains an explicit human/operator mode only.

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
observed, Escape restores the bound focus identity, and the previously
frontmost app is restored. AX coverage never passes `--activate`.

The coordinator reports `blocked_gui_locked` (exit 3) when `lsappinfo front` is
`loginwindow`; this is an honest red result, not a fixture or browser substitute.
