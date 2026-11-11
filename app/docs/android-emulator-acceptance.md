# Android emulator acceptance

The October 3 startup incident ([#20437](https://github.com/BasedHardware/omi/pull/20437))
passed host tests but reproduced in Android's actual foreground-service command
queue. Mobile App Checks therefore runs **Android Emulator Acceptance** alongside
the existing arm64 compile/JVM checks. It runs for full-tier Android/startup/WAL
PR inputs, applicable main pushes, and nightly. A selected failure, cancellation
or unexpected skip blocks **Mobile Release Eligibility**; the existing Codemagic
source-admission verifier requires both that aggregate and a successful,
non-skipped **Android Emulator Acceptance** job on the exact source SHA before
an Android tag build.

## Two measured layers

1. `android_fgs_probe.py` compiles the actual sync-service sources and executes
   five scenarios five times: immediate cancellation, 100 start/stop pairs plus
   an active transfer, restart, orphan stop and background cancellation. It
   requires real foreground promotion, continued active transfer, and no leaked
   notification/service/wake lock. Host tests cannot prove this Android ordering.
2. `android_startup_smoke.py` installs a whole minified **dev/local_dev AOT APK**
   and cold-launches it three times offline. Each launch must render Get Started,
   survive at least 20 seconds in the same process, and report no fatal/ANR.
   Fresh install plus force-stop covers first-run and persisted logged-out launch.
   A tiny instrumentation in the native probe reads real accessibility nodes
   directly, without waiting for an animated screen to become idle.
   The existing arm64 compile remains; CI uses one x86_64 ABI for the emulator.

The workflow builds with local Firebase fixtures and public debug signing. The
emulator runner enables airplane mode and disables Wi-Fi/cellular data before
installation and checks `Active default network: none` before and after every
launch. No credentials, customers or remote backend are needed. It refuses
physical devices, API levels below 36 and any emulator with Omi already installed;
it never clears existing account data. It force-stops/uninstalls its own APK and
restores network settings even after failure. Use an isolated AVD, not a developer
emulator that owns valuable app state.

## Exact-source release admission

Android full-release and production Shorebird-patch tag builds call the shared
`app/scripts/admit_android_source.sh`, which passes `--platform android` to the
authenticated collector and offline verifier. Both refuse publication without
exact-source acceptance; patch tags must also identify the checked-out source. A green aggregate with conditionally skipped app jobs is not
Android acceptance. The collector verifies the canonical workflow/run/job,
main branch, source SHA, success and first attempt. PR and nightly results
cannot admit a release; a push or explicit manual run on main can.

When tagging a source whose ordinary main-push job was inapplicable, run the
existing workflow explicitly (`gh workflow run mobile-app-checks.yml --ref main`),
wait for successful **Android Emulator Acceptance**, then tag that exact tested
commit. If main advances, tag the tested SHA rather than assuming the new tip is
covered. A past main commit without its own successful emulator proof is
intentionally blocked: a manual run cannot retroactively prove an arbitrary
older SHA. Select the current main candidate, run acceptance, and tag that tested
SHA. Older main commits remain admissible only when they already have exact-SHA
acceptance evidence. The manual run does not replace the required canonical push aggregate
or Release Eligibility proof. No production publication occurs in this workflow.

## Local commands and evidence

With Java 21, Gradle 8.14.2, SDK 36/build-tools 36.0.0 and a fresh Android 16 AVD, run the
native probe first (it also installs the accessibility instrumentation):

```sh
python3 app/scripts/android_fgs_probe.py --serial emulator-5554 --gradle /path/to/gradle \
  --rounds 5 --output /tmp/android-acceptance/native
python3 app/scripts/android_startup_smoke.py --serial emulator-5554 \
  --apk /absolute/path/app-dev-release.apk \
  --aapt "$ANDROID_HOME/build-tools/36.0.0/aapt" \
  --rounds 3 --output /tmp/android-acceptance/startup
```

Build the fixture APK using the workflow's input preparation and
`flutter build apk --release --flavor dev --target-platform android-arm64
--dart-define=OMI_APP_PROFILE=local_dev` on an arm64 host (CI uses `android-x64`).
The offline contract tests are `python3 app/scripts/android_startup_smoke_test.py`.

CI uploads `android-acceptance-<sha>` for 14 days, including logcat, screenshots,
UI hierarchy and JSON receipts, even after failure. Receipts identify the APK
package/version/hash and API/boot ID. `runner_source_sha` identifies the smoke
runner revision, not an assertion about the APK's source: callers testing a
store artifact must separately retain its build/source/signature receipt.
The native probe compiles this checkout's production service and records its
`source_sha`. A missing or failed receipt is never equivalent to acceptance.

## Limits and next layer

This is native-service and fixture-configured packaged startup acceptance. It is
not a signed Play split-install check, authenticated/upgrade journey, physical
BLE recording, OEM battery-policy test or a statistical beta crash-rate gate.
The smoke runner also accepts `com.friend.ios` APKs for a deliberate **offline**
exact-artifact check on a fresh local emulator; retain the signed AAB hash and
build provenance if reconstructing/re-signing a universal APK.

Codemagic's Apple-silicon VMs do not support nested Android virtualization, so
emulator checks run on GitHub Linux/KVM. Do not put an unexecutable emulator step
in the existing macOS publishing lane. Broader test-track soak/telemetry admission
remains a separate layer; a short session or zero reported crashes without enough
exercised launches cannot prove a safe release.
