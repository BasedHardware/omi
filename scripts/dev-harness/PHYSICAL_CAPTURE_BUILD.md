# Isolated real-app capture build

**Experimental host.** This builder has produced signed artifacts, but the full
capture/recovery/upload sequence has not passed on hardware. Its build receipt
is compilation/provenance evidence only. See [status and measured layers](IPHONE_HARNESS.md).

`physical_capture_build.py` generates a single-target Xcode project outside the
repository. It builds `integration_test/physical_capture_main.dart` in profile
mode, using the real Flutter app, CaptureProvider, WAL, and copied Runner native
BLE and phone microphone modules. Profile mode supports termination and launch
without an attached Flutter debugger.

Compilation disables Xcode signing. The builder then embeds the explicitly
supplied development profile and signs nested frameworks and the application
with the supplied identity and minimal bundle-specific entitlements. This works
with Xcode-managed wildcard profiles without creating provisioning resources.

The generated host adopts Flutter's scene lifecycle for iOS 27. Its copied
AppDelegate registers the original bridges through `FlutterImplicitEngineDelegate`
using the created engine's messenger and registry. `FlutterSceneDelegate` owns
the real Main storyboard and view hierarchy; custom BLE foreground/background
hooks are retained. This adaptation qualifies this host only and does not change
or certify the shipping application's scene lifecycle.
The qualification scene disables its idle timer while active and restores normal
idle behavior when it resigns active or enters the background, so foreground
diagnostic waits do not require repeated phone unlocks.

This is limited capture qualification. Watch/widget extensions, ordinary Omi
entitlements, production deep links, GoogleService configuration, and the native
Crashlytics, Messaging, Intercom, and PostHog plugins are excluded. The generated
Info.plist disables Firebase Messaging auto-init, Crashlytics collection, general
Firebase collection, Firebase delegate proxying, and PostHog auto-init before
native plugin registration. Firebase Core and Auth remain for the private auth
emulator. Core's native registration only initializes default Firebase options
when a GoogleService plist exists; this builder excludes that file. Auth plugin
registration binds channels; the qualification entrypoint selects its emulator.

The normal Runner source and generated registrant are never edited by this
builder. Every invocation refreshes the native source copy and removes stale
files that disappeared from the source tree. Target, source-list,
SDK, or dependency changes regenerate Xcode and reintegrate CocoaPods; Dart-only
scenario changes reuse the existing native project. Run after entrypoint changes are ready.
It does not install, launch, or contact a phone. The bundle identifier must
contain `.capture-qualification.` and its displayed title is `OmiCaptureQA`.

Required CLI parameters are shown by `python3
scripts/dev-harness/physical_capture_build.py --help`. Supply the app root,
external output directory, Flutter SDK root, explicit bundle/team/profile/signing
identity, private fixture API and auth emulator addresses, and a fixture UID
starting with `omi-physical-fixture-`. No device or signing identifiers belong in
this document or Git. `--prepare-only` resolves dependencies without compiling.
`--capture-source phone_mic` is the default. Use `--capture-source wearable` with
a separate qualification bundle, fixture UID and API port for discovery-based
BLE qualification. An optional `--wearable-id` also selects the wearable source.

Generated `build-receipt.json` records native and Dart input hashes, commit,
verified registry exclusions, compile defines, product path and every signed app
file hash (including the Flutter AOT payload), plus a deterministic tree digest.
It rejects Dart inputs changing during compilation. The builder verifies the signed
app with `codesign --verify --deep --strict`, checks identity and Firebase flags
in its final Info.plist, and rejects a bundled GoogleService plist or extensions.
Both Main and LaunchScreen storyboards are explicit resource inputs. The builder
requires their compiled storyboard directories in the finished app and checks
that the scene configuration points to Main before signing and issuing a receipt.
Logs are saved alongside the receipt. Compilation and signature verification are
separate from physical capture acceptance, BLE pairing, recovery, upload behavior,
network observations, and user permission interactions; those require device-run
evidence from the device owner.
