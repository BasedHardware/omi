# `omi_device` (C++)

Omi device protocol helpers: GATT UUIDs, the 3-byte packet header strip, STT URL
builders, and a BLE surface you bind to your own platform stack.

**No third-party dependencies.** `cmake -S . -B build && cmake --build build`.

## Protocol only

```cpp
#include "omi/device/protocol.hpp"

auto payload = omi::device::StripPacketHeader(data, len);  // drops 3 bytes
```

## BLE

This package ships no BLE implementation. Cross-platform C++ BLE libraries are
either OS-specific or non-permissively licensed, so `omi::device` takes the stack
as an interface and the Omi clients that speak BLE (Python/Swift/React
Native/Flutter) bind their own. Implement `BleBackend` against CoreBluetooth
(Apple), `Windows.Devices.Bluetooth` (WinRT), or BlueZ (Linux):

```cpp
#include "omi/device/ble.hpp"

class MyBackend : public omi::device::BleBackend {
 public:
  std::vector<omi::device::BleDevice> Scan(int timeout_ms) override {
    // ... platform scan, return {id, name, rssi} ...
  }

  void Notify(const std::string& device_id, const std::string& service_uuid,
              const std::string& characteristic_uuid,
              omi::device::PacketCallback on_packet) override {
    // ... connect, subscribe, call on_packet(bytes) per notification,
    //     block until disconnect ...
  }
};

omi::device::SetBleBackend(std::make_shared<MyBackend>());

for (const auto& device : omi::device::Scan(5000)) { /* ... */ }

// Raw notifications, header included:
omi::device::Listen(device_id, [](const std::vector<std::uint8_t>& packet) { /* ... */ });

// Header already stripped:
omi::device::ListenPayload(device_id, [](const std::vector<std::uint8_t>& pcm_or_opus) { /* ... */ });
```

`Listen` subscribes to `kAudioDataUuid` on `kServiceUuid`. Without a backend,
`Scan`/`Listen`/`ListenPayload` throw `omi::device::BleDisabled`.

## Migrating from `-DOMI_DEVICE_BLE=ON`

That flag and `-DOMI_DEVICE_SIMPLEBLE_SOURCE_DIR` are gone, along with the
SimpleBLE dependency they pulled in. Passing either is a hard configure error
that points here rather than a silent no-op. Implement `BleBackend` as above and
install it with `SetBleBackend()`; `Scan`/`Listen`/`ListenPayload` are unchanged.

## Tests

```sh
cmake -S . -B build -DOMI_DEVICE_BUILD_TESTS=ON && cmake --build build && ctest --test-dir build
```
