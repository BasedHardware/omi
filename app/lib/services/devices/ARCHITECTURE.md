# Native device readiness and Limitless audio

Native BLE owns bonding, connection attempts, and automatic reconnection.
`DeviceService` retains its connection and `NativeBleTransport` after the
60-second launch timeout and, with saved reconnect enabled, transient adapter or
native fail-to-connect errors before readiness. Device-specific setup errors after
readiness still tear down partial connections. `SavedPendantReconnect` owns one
Dart attempt at a time and a 5-second exponential backoff capped at five minutes,
also ensuring the saved BLE pairing on resume and adapter-on. It reuses the same
connection/transport; native owns the radio retries. Only explicit user disconnect and
Forget persist suppression; DFU and capture recovery release the link without
revoking reconnect intent. DFU temporarily pauses the scheduler until completion.
Saved-target changes disarm and unmanage the previous target before connecting
the replacement (including a switch to a non-BLE input). The stale-bond block
still requires explicit user recovery.

This fix ships default ON per owner approval. Only boolean PostHog
`saved-pendant-reconnect-kill=true` disables the new policy; missing, unreachable,
or variant-valued flags leave it ON. Launch reads the cache synchronously;
background refresh at start/resume and every five minutes applies a late kill
without gating connection attempts. Disabling cancels the new timer/native policy
and preserves the legacy one-shot launch connect, ignoring the new persisted
blocks and creating no new ones. iOS derives eligibility
from Dart's saved pairing rather than persisting the scan-discovered peripheral
set. Android preserves its existing native retry loop and makes repeated Dart
manage requests idempotent, with user-disconnect protection for queued starts.
`Saved Pendant Reconnect` records bounded trigger/result fields, attempt count,
and time since the observed disconnect (launch time if the prior process's
outage start is unknown); native and Dart counters are separate series. Each owner reports at most seven
distinct intermediate states plus connected per outage; retry ticks still advance
the attempt counter but do not each emit an event. The consumer separately counts
attempted episodes, connected outcomes, and their rate.

A later `BleBridge.onDeviceReady` can therefore
publish a connected device without returning through the original `connect()`.
Bluetooth readiness alone does not establish the pendant's audio mode.

`LimitlessDeviceConnection` keeps its readiness subscription after retained launch failures.
Its first late ready completes the existing clock-observation, time-sync, and
stream-selection pipeline. Later ready events use the existing reconnect setup.
The existing connection epoch fences each asynchronous setup continuation;
explicit disconnect closes the owner before releasing subscriptions. Network
recovery shares the reconnect setup, and cannot revive a retired connection.
The first late setup retries a control failure once. Persistent failures remain
diagnostic failures; a working BLE bond or microphone is not inferred from them.

Capture can subscribe to the connector's audio stream while setup settles.
Decoded frames still pass through the existing capture policy, source, WAL, and
transcription pipeline. Transcribe Later suppresses realtime activation, including
when selected during initial setup. This repair does not erase device storage,
change subscription entitlements, or recover audio from earlier gaps.

Implementation and acceptance checklist:

- [x] Late first readiness starts the actual clock/stream commands and delivers
  decoded golden audio through the real native bridge into an early subscriber.
- [x] Disconnect and newer connection epochs fence delayed setup and network/mode
  callbacks; transient retry is bounded and teardown leaves no timers.
- [x] Transcribe Later stays suppressed, including an in-flight activation change.
- [x] Existing protocol vectors, reconnect ordering, and clock-drift tests pass.
- [ ] Merge, store release, and physical iOS/Android Limitless range-loss checks.
- [ ] Match the customer's hardware, versions, and failed recording to this cause;
  assess transcript quality and subscription/return questions privately.

Regression: `app/test/services/devices/saved_pendant_launch_timeout_reconnect_test.dart`.
Related reports: #15500 and #20626; neither is closed solely by this code repair.
