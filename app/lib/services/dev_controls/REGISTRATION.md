# B0: execute registration before trusting a control surface

Repaired. The five VM extensions register as `ext.omi.controls.*` — Dart's
`registerExtension` requires the `ext.` prefix, so the previous
`omi.controls.*` names threw `ArgumentError` the first time the surface was
actually enabled. Capabilities advertise exactly the five suffixes
`capabilities`, `state`, `wait_ready`, `navigate`, `fault`. There is no
generic `action`; `fault` takes the existing `fault`/`clear` parameters.
Prefixing each suffix with `ext.omi.controls.` is the installed set. Invalid
name aliases are not registered.

`installIfEligible` accepts a registrar seam; the default is the Dart SDK
function. Eligibility (`kDebugMode` + `local_dev` + `OMI_DEV_CONTROLS=1`)
runs before the seam. Installed is set only after every registration returns.
`app/test.sh` executes `app/test/spine/b0_registration_test.dart` in a
separate opt-in compilation: that test records every production registration,
calls the real `developer.registerExtension` for each, then invokes the
capabilities handler. `semantic_controls_guard_test.dart` remains the
ordinary-build authority. The seam cannot bypass the eligibility gate. The
Dart 3.12 SDK shipped with Flutter 3.44.5 is the wire authority
(`lib/developer/extension.dart`).
