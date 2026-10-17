# Native device readiness and Limitless audio

Native BLE owns bonding, connection attempts, and automatic reconnection.
`DeviceService` retains its connection and `NativeBleTransport` after the
60-second launch timeout. A later `BleBridge.onDeviceReady` can therefore
publish a connected device without returning through the original `connect()`.
Bluetooth readiness alone does not establish the pendant's audio mode.

`LimitlessDeviceConnection` keeps its readiness subscription after that timeout.
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
