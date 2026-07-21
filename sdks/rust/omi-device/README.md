# omi-device

`omi-device` is a Rust protocol SDK for the current Omi BLE firmware. It provides Omi discovery filtering, a host-BLE connection abstraction, the documented GATT UUIDs, device commands, and ring-storage codecs.

The crate deliberately does not choose a BLE runtime. Implement `BleAdapter` and `BleConnection` with the platform/runtime your application already uses, then call `discover_omi` and `connect_omi`.

```rust
use omi_device::{connect_omi, discover_omi, BleAdapter};

let devices = discover_omi(&mut adapter)?;
let mut device = connect_omi(&mut adapter, &devices[0].id)?;
device.sync_time(epoch_seconds)?;
let battery_percent = device.battery_level()?;
```

The ring storage API follows firmware 3.0.20+: status reads are four little-endian `u32` values, while ring control fields are big-endian. The [maintained client protocol reference](../../../app/lib/services/devices/ring_protocol.dart) defines the corresponding wire layout. `RingRecordReassembler` accepts unaligned data notifications and returns 444-byte records.
