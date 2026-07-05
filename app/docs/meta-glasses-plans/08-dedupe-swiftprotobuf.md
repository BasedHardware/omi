# 08 — Dedupe SwiftProtobuf

## Goal
Eliminate the runtime objc warning that two copies of SwiftProtobuf are linked
(one inside `MWDATCore.framework`, one in the Runner binary). objc warns this
"may cause spurious casting failures and mysterious crashes" — real risk in a
production app.

## Grounding
- Launch log shows: `Class _TtC13SwiftProtobuf... is implemented in both .../MWDATCore.framework/MWDATCore and .../Runner.app/Runner`.
- Meta's DAT xcframeworks statically embed SwiftProtobuf. A CocoaPods dependency in the app also pulls SwiftProtobuf into the Runner binary. Find it: `grep -i swiftprotobuf ios/Podfile.lock` and check the dependency tree (`ios/Pods/`), plus any SPM package products.

## Steps
1. Identify the pod(s) that transitively depend on SwiftProtobuf (candidates: Firebase/gRPC-related, analytics SDKs). `cd ios && pod dependencies` or inspect `Podfile.lock`'s `SPEC DEPENDENCIES` / `DEPENDENCIES` graph.
2. Choose the least invasive fix, in order of preference:
   - a. If the pod offers a build option to use a **dynamic** SwiftProtobuf or to not statically link it, enable that so only one copy resolves at load.
   - b. Pin the app-side SwiftProtobuf to the **same version** MWDATCore embeds, so the duplicate classes are identical (removes the correctness risk even if the warning persists) — verify the embedded version from the xcframework.
   - c. As a last resort, wrap the offending pod in `use_frameworks!`/modular headers config in the `Podfile` so linkage is dynamic.
3. Do NOT modify Meta's xcframeworks. The fix is on the app/pod side only.
4. Rebuild (`Profile-dev`, unsigned), install, and confirm the `implemented in both` warnings are gone from the launch console.

## Tests
- No unit test; this is a native linkage fix. Verify by the absence of the duplicate-class warnings in `devicectl ... launch --console` output and a clean release build (`rm -rf .build && xcrun swift build -c release` equivalent for the workspace).

## Acceptance
- Launch console shows zero `SwiftProtobuf ... implemented in both` lines.
- App still builds, signs, installs, and the Meta DAT flow (registration + capture) works.
- No change to the default install target's behavior otherwise.
