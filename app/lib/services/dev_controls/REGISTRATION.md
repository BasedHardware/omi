# B0: execute registration before trusting a control surface

Builder: App UI B0; land independently before B1. The defect is an unexecuted
registration path: Dart rejects all five current `omi.controls.*` names.
Rename them to `ext.omi.controls.*`. Keep v1 and exactly five methods:
`capabilities`, `state`, `wait_ready`, `navigate`, `fault`. Remove the false
`action`, `fault.arm`, and `fault.clear` capability claims; `fault` takes the
existing `fault`/`clear` parameters. B1 does **not** add generic action.
Capabilities list suffixes, so prefixing each with `ext.omi.controls.` must give
exactly the installed set. Do not register invalid-name aliases.

`installIfEligible` now accepts a registrar seam; the default remains the Dart
SDK function and the eligibility check runs before the seam. This is a
behavior-preserving refactor, not the repair. `app/test.sh` executes the B0
spine test in a separate opt-in compilation before the ordinary, unopted-in
suite. That test records every production registration, calls the real
`developer.registerExtension` for each, then invokes the actual capabilities
handler. It currently fails for Dart's real ArgumentError, converted to an
assertion by collecting all registration errors. No fake registrar-only test
can establish SDK compatibility. Successful pending execution fails XPASS.

Preserve `semantic_controls_guard_test.dart` and its ordinary-build coverage.
Never supply a runtime eligibility override. The seam cannot bypass debug +
local_dev + OMI_DEV_CONTROLS=1. Mark installed only after registrations succeed
when implementing B0. No simulator, auth service, or production endpoint is
needed. The Dart 3.12 SDK shipped with Flutter 3.44.5 is the wire authority
(`lib/developer/extension.dart`, `registerExtension` requires `ext.`).
