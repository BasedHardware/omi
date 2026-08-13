# macOS semantic evidence probe

`native-semantic-evidence.swift` observes a scratch shell without activating it
for AX snapshots. It reads only bounded, allowlisted AX role/name tokens and can
post an explicitly opted-in CoreGraphics key sequence; it does not take
screenshots or inspect page JavaScript. Generic runs are always
`supplementary_observation`.

Use the shell's default off-screen accessory mode for screenshots, runtime
probes, and AX snapshots. For keyboard traces, launch the scratch shell with
`OMI_SEMANTIC_WINDOW=1` instead of `OMI_HEADED=1`. That mode orders a small
accessory window behind the user's windows without activating it. The probe can
temporarily activate the target for the bounded key sequence, then hides the
scratch window and restores the app that was previously frontmost before it
emits evidence. The batch coordinator refuses keyboard coordinates by default
with `blocked_user_focus`; an operator must explicitly set
`OMI_ALLOW_TEMPORARY_FOCUS=1` for a run where that brief activation is
acceptable. `OMI_HEADED=1` remains an explicit human/operator mode only.

Compile it on macOS with:

```sh
swiftc -O -framework AppKit -framework ApplicationServices -framework CoreGraphics \
  -o /tmp/omi-native-semantic-evidence native-semantic-evidence.swift
```

Matrix evidence must be run through `native-semantic-evidence-batch.mjs` with an
exact `omi.polish.matrix-manifest/v1` coordinate and a prepared scratch `.app`:

```sh
node shells/macos/probes/native-semantic-evidence-batch.mjs \
  --manifest .build/semantic/matrix.json \
  --out-root .build/semantic \
  --probe .build/semantic/native-semantic-evidence \
  --fixture-app .build/native-fixture/build/macos/omi-on-polish-batch.app \
  --prepare
node shells/macos/probes/native-semantic-evidence-batch.mjs \
  --manifest .build/semantic/matrix.json \
  --out-root .build/semantic \
  --prepared-input-set .build/semantic/prepared-input-set.json \
  --replay-proof
```

Preparation binds every regular bundle file, `Info.plist` bundle identity, and
the exact `omi-on-*` executable into the immutable input set. Capture launches
that executable directly with a fixture-only surface query and an isolated
runtime home, waits a bounded time for its `background-semantic` readiness
signal, probes the launched runtime PID, and terminates that exact child. It
never uses `open`, AppleScript, a pre-existing PID, a shipping bundle, API
configuration, or broad process-name kills. Runtime PIDs are checked but
redacted from evidence, sidecars, batch results, and receipts, so replaying
copied inputs recreates the target while retaining byte-identical canonical
artifacts. `native_live` manifests fail closed at this producer boundary.

Keyboard coverage is accepted only when every target transition is observed,
Escape restores the bound focus identity, and the previously frontmost app is
restored. AX coverage never passes `--activate`; the coordinator also verifies
that the foreground application is unchanged across launch, probe, and cleanup.
