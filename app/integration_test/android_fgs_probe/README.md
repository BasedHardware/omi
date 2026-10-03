# Android foreground-service cancellation probe

Reproduces the October 2026 startup incident with the actual
`SyncTransferForegroundService` and its two production dependencies. The probe
has no Flutter, Firebase, network permission, credentials, or user accounts.
Its package is `com.omi.fgsprobe`; it does not install over Omi.

With Java 21, SDK 36, Gradle 8.14.2, and an isolated Android 16 emulator:

```sh
python3 app/scripts/android_fgs_probe.py --serial emulator-5554 --rounds 5 \
  --output /tmp/omi-fgs-evidence --gradle /path/to/gradle
```

A clean checkout has no `app/android/gradlew`: pass an installed Gradle 8.14.2
executable with `--gradle` as above. If the Flutter app was already bootstrapped,
`(cd app && flutter build apk --debug --flavor dev --target-platform android-arm64 --config-only)`
generates the wrapper, which the runner uses by default. A missing executable
fails with setup instructions; the build has a ten-minute timeout.
The runner compiles fresh production sources, then exercises immediate stop,
100 start/stop pairs, stop followed by restart, stop with no active service, and cancellation after moving the task to the background.
Each case starts a fresh process and must survive while releasing its service,
notification, and partial wake lock. Logcat and a JSON result receipt go to the
output directory. The runner refuses physical devices and older Android images.

At source `147f77d86a2d`, immediate stop kills the probe with
`RemoteServiceException$ForegroundServiceDidNotStartInTimeException`. An
`onCreate` promotion alone does not repair an already cancelled pending start.
The companion hermetic tests run with `:app:testDevDebugUnitTest`. Mobile App
Checks now runs this probe and minified AOT startup acceptance on an Android 16
Linux emulator. A selected failure or unexpected skip in an active full-tier run
blocks Mobile Release Eligibility (unapproved fork CI is deliberately deferred),
which Codemagic's existing source-admission gate requires. See the
[acceptance guide](../../docs/android-emulator-acceptance.md).

The runner writes `receipt.json` with source SHA, probe APK hash, API level,
boot ID and every case result. A failed/incomplete run cannot leave a stale
passing receipt. Android still enforces its foreground-service deadline; a
bounded 60-second case wait accommodates host contention and Activity.onStop
without skipping the actual promotion, lifecycle or cleanup assertions.
