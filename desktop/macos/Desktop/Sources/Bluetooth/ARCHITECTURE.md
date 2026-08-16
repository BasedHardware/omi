# Bluetooth Architecture

The Bluetooth stack separates physical CoreBluetooth events from the logical
device session shown by the app. One type owns each kind of state:

```
BluetoothManager (central events and discovery)
  -> BLEPhysicalDriving (CoreBluetooth side effects)
  -> BleTransport (one physical transport generation)
  -> BaseDeviceConnection (one device lifecycle generation)
  -> DeviceSessionCoordinator (canonical logical session)
  -> DeviceProvider (read-only UI projection)
```

## Ownership

- `BluetoothManager` owns scanning, discovered peripherals, typed central
  events, and per-peripheral connection leases. Connection lifecycle must not
  be broadcast through `NotificationCenter`.
- `BleTransport` owns characteristic discovery, reads, writes, notification
  broadcasts, and physical disposal for one `sessionGeneration`.
- `BaseDeviceConnection` owns the shared connect/prepare/teardown sequence.
  Device subclasses implement only `prepareDeviceAfterConnect`,
  `teardownDevice`, and (when needed) `performDeviceUnpair`.
- `DeviceSessionCoordinator` is the sole authority for logical phases, pairing,
  active connection identity, reconnect scheduling, and generation fencing.
- `DeviceProvider` publishes the coordinator snapshot and display-oriented
  battery/storage/firmware state. It must not maintain parallel connection
  booleans, active-connection storage, or reconnect timers.

## Reliability contracts

1. Every logical connect attempt receives a monotonically increasing
   generation. Callbacks from any older connection are ignored.
   CoreBluetooth connection callbacks additionally carry a manager lease token;
   a cancelled lease remains fenced until a terminal central callback or
   explicit central reset, so a replacement transport cannot consume it.
   Scheduled reconnects carry their generation and attempt back into the
   coordinator for revalidation immediately before connection starts.
   Only failures from a validated reconnect request schedule another retry;
   an explicit selection failure never falls back to a previously paired
   device.
2. `DeviceOperationBroker` owns callback, timeout, cancellation, and disconnect
   races. A handle includes both key and token; a key alone never completes an
   operation. Callback completion drains the physical start task before the
   waiter resumes, so a device response cannot outrun its BLE write callback.
3. CoreBluetooth and several device protocols return only a characteristic or
   command key, with no token. If such an operation terminates before its
   callback arrives, `UncorrelatedOperationGate` poisons that key until teardown.
   Retrying in the same physical session would let the old callback masquerade
   as the new response.
4. Adapter commands that share one BLE write characteristic run through
   `DeviceCommandQueue`. Command IDs can correlate device responses, but they
   cannot make simultaneous characteristic write callbacks distinguishable.
   Teardown closes and drains the queue before response brokers are reset.
5. Characteristic notifications are multicast with one continuation per
   subscriber. Cancelling a consumer removes only that subscriber; later
   subscribers can restart within the same physical session.
6. Bee and PLAUD audio use `DeviceAudioStreamController`: the first subscriber
   owns setup, the last subscriber leaving cancels and joins setup before a
   compensating stop, and every subscriber receives every active-session frame.
   Frames observed during setup or teardown are dropped. A stop that cannot be
   confirmed fences the controller and disconnects the physical session; it
   never layers a replacement recording over ambiguous state.
7. A connection object represents exactly one session generation. Shared setup
   runs once, and every explicit or unexpected teardown path joins one retained
   teardown task through device cleanup and transport disposal.
8. Disposal first claims the transport, then drains all waiters and streams,
   requests physical disconnect exactly once, and finally detaches delegates.

## Testing seams

- Inject `DeviceOperationClock` to advance timeouts without wall-clock sleeps.
- Inject `DeviceSessionScheduling` to drive reconnect policy deterministically.
- Inject `BLEPhysicalDriving` to test transport disposal without Bluetooth
  hardware or private CoreBluetooth initializers.
- Use a fake `DeviceTransport` to exercise the production
  `BaseDeviceConnection` template lifecycle.

When adding a device, put device-specific protocol parsing in a connection
subclass and keep lifecycle ownership in the base/coordinator layers. When a
wire response cannot carry a correlation token, use the shared uncorrelated
operation gate rather than a raw continuation dictionary or ad-hoc timeout.
