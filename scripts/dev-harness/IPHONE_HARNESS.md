# iPhone capture regression tools for agents

Start here when changing phone microphone lifecycle, wearable transport, device
discovery, or physical-test infrastructure. The offline suites need no iPhone,
Apple signing identity, account, backend, or retained personal-device files.
They execute production controller/transport policy with fake OS I/O and
synthetic payloads. A passing replay is not a new hardware acceptance result.

## Work without a phone

From the repository root after the normal component bootstrap:

```sh
# Analyzer, discovery, collector and fixture failure/happy paths (Python).
bash scripts/dev-harness/run-tests.sh

# Production microphone controller policy and eight canonical vectors (macOS).
ruby app/ios/test/phone_mic_lifecycle_replay_test.rb

# Compile the native probes against the real iPhone SDK, without signing (macOS).
python3 app/ios/test/phone_mic_probe/build.py --check

# Production Dart BLE transport: existing listener survives reconnect.
(cd app && flutter test test/unit/wearable_radio_trace_replay_test.dart)

# Bounded experimental capture always stops after failure/timeout.
(cd app && flutter test test/unit/physical_capture_lifecycle_test.dart)

# Opt-in qualification guard remains off for ordinary builds.
(cd app && flutter test test/unit/physical_qualification_test.dart)
(cd app && flutter test --dart-define=OMI_PHYSICAL_QUALIFICATION=true test/unit/physical_qualification_test.dart)
```

Use the repository's configured Flutter SDK. Python dependencies are resolved by
the existing harness runner; Flutter tests require the normal `app/` bootstrap.
The native commands require Xcode's iPhone SDK on macOS; Python and Dart tests
do not require Xcode or hardware. These checks are part of the existing harness,
mobile test suite, and macOS manifest lanes. Component verification still uses
`make mobile-verify ARGS="fast --all"` and `make preflight`.

The microphone replay always covers foreground return, both interruption resume
flags, permission denial/restoration, engine epochs, and late-frame rejection.
The BLE suite includes a reviewed reduction from the device session: audio
arrived before notification-subscription confirmation on both links, and the
original Dart listener survived disconnect/reconnect. Its payloads are synthetic;
the reduced scenario contains no device identity or recorded audio.

When investigating a newly observed failure, reduce its event order to a
sanitized regression case in the owning suite and add the expected assertion.
Do not turn an observed failure into the new expected behavior. Optional local
trace inputs and their prerequisite analyzers are documented in the
[native probe guide](../../app/ios/test/phone_mic_probe/README.md#replay-without-an-iphone).
The committed suites work with those environment variables unset.

## Choose the right measured layer

| Tool | Usable result | Limit |
| --- | --- | --- |
| Native mic replay | Production controller policy under deterministic lifecycle events | Fake OS I/O and PCM; no AVAudioSession hardware qualification |
| Dart wearable replay | Production NativeBleTransport/BleBridge listener and subscription behavior | No CoreBluetooth, shipping BLE manager, codec or upload qualification |
| Native mic/wearable probe | Bounded metadata-only capture on an authorized phone | Separate native app; no Flutter/WAL/upload measurement |
| Probe analyzers | Build matching, required scenario status, permission pairs, sampled resource metrics | JSON attribution is not independent proof of a real device run |
| Permission UI helper | Named diagnostic-app permission switch/consent assertions | Requires authorized unlocked phone; collect denied/restored capture separately |
| Isolated Flutter capture, fixture API and collector | Experimental finalized-WAL recovery/upload workflow and hermetic evidence checks | Full physical sequence has not passed; do not use as a release gate |
| Interruption driver | Experimental stimulus trace with explicit failed/incomplete status | No successful physical interruption/recovery qualification |

## Device-session findings retained for context

The 2026-09-22 operator-assisted session used an iPhone 15 Pro Max on iOS 27.
These are observations from retained local signed artifacts and matching traces,
not claims that this PR's final source was subsequently installed on hardware:

- Native microphone foreground/background capture and stop behavior passed.
- The standalone radio observer recorded wearable reconnect and packet delivery
  while the phone was locked. Production Dart transport replay passed separately.
- Microphone and Bluetooth denial/restoration passed using chronologically
  ordered receipts from the same v5 probe build; both permissions were restored.
- An uninterrupted five-minute native mic run delivered 3,000 frames, about
  2.16% mean CPU of one core, about 63 MB maximum resident memory, and 120 ms
  maximum frame gap. This includes probe instrumentation overhead and is not
  a shipping-app performance budget, battery measurement, or zero-loss claim.
- The operator confirmed voice Siri during a later 120-second run. That trace
  delivered 1,200 frames but recorded no interruption begin/end pair. Recovery
  remains unobserved. CallKit stimulus attempts also failed before establishing
  an interruption; they do not establish a shipping-app defect.
- The isolated full Flutter app built and rendered onboarding after generated
  scene/storyboard repairs, but its capture entry failed with StateError before
  an accepted recovery/upload run. A later diagnostic build was signed but not
  installed. Phone and wearable full-app recovery remain unqualified.

Raw traces, signed apps, provisioning profiles, identifiers, recorded WAL files,
and device screenshots stay outside Git. No personal phone is registered for
future agents. The original phone session has ended; these instructions grant
no continuing device access and require no additional human test to use offline.

## Explicitly authorized future physical work

Use the [native probe guide](../../app/ios/test/phone_mic_probe/README.md) and
[permission helper](../../app/ios/test/phone_probe_ui/README.md) for a bounded
interactive session. Keep each signed build and its matching trace together;
verify startup before asking an operator to record. Analyzer exits are 0 for
required checks passed, 1 for failed checks, and 2 for incomplete/unobserved or
invalid evidence. Never infer interruption recovery from uninterrupted frames.

For experimental full-app work, start with [capture status and admission](physical_capture.md),
then [build](PHYSICAL_CAPTURE_BUILD.md), [private synthetic fixtures](physical_capture_fixtures/README.md),
and [host collection](physical_capture_collect.md). Diagnose the entry stage and
sanitized runtime stack before repeating capture. The collector defaults to an
offline plan; execution requires a separately authorized phone session and an
installed isolated bundle. Copied artifact consistency always reports
`hardware_qualified:false`; it is not a substitute for observed device operations.

Dedicated unattended devices continue to use the existing
[registry and lease contract](PHYSICAL_DEVICES.md). A borrowed phone must not be
registered as dedicated. Never replace the ordinary Omi app for these tests.
