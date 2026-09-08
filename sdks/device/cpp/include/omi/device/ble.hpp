#pragma once

#include "omi/device/protocol.hpp"

#include <cstdint>
#include <functional>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace omi {
namespace device {

struct BleDevice {
  std::string id;
  std::string name;
  int rssi = 0;
};

using PacketCallback = std::function<void(const std::vector<std::uint8_t>&)>;

// Thrown by Scan/Listen/ListenPayload when no backend has been installed.
class BleDisabled : public std::runtime_error {
 public:
  BleDisabled()
      : std::runtime_error(
            "omi::device: no BLE backend installed; call SetBleBackend() with a "
            "platform stack (see sdks/device/cpp/README.md)") {}
};

// The platform BLE stack, supplied by the embedding application.
//
// This package ships no third-party BLE dependency: cross-platform C++ BLE
// libraries are either OS-specific or non-permissively licensed, and the Omi
// clients that do speak BLE (Python/Swift/React Native/Flutter) already bind
// their own stack. Implement this against CoreBluetooth (Apple),
// Windows.Devices.Bluetooth (WinRT), or BlueZ (Linux).
class BleBackend {
 public:
  virtual ~BleBackend() = default;

  // Discover nearby peripherals, scanning for up to timeout_ms.
  virtual std::vector<BleDevice> Scan(int timeout_ms) = 0;

  // Connect to device_id, subscribe to characteristic_uuid on service_uuid, and
  // invoke on_packet with each raw notification. Blocks until disconnect.
  virtual void Notify(const std::string& device_id, const std::string& service_uuid,
                      const std::string& characteristic_uuid, PacketCallback on_packet) = 0;
};

// Installs the backend used by Scan/Listen/ListenPayload. Pass nullptr to clear.
void SetBleBackend(std::shared_ptr<BleBackend> backend);
std::shared_ptr<BleBackend> GetBleBackend();

// Discover nearby devices. Throws BleDisabled without a backend.
std::vector<BleDevice> Scan(int timeout_ms = 5000);

// Notify on kAudioDataUuid, invoke callback with raw bytes (header included).
// Blocks until disconnect. Throws BleDisabled without a backend.
void Listen(const std::string& device_id, PacketCallback callback);

// Same as Listen but strips the 3-byte Omi packet header before callback.
void ListenPayload(const std::string& device_id, PacketCallback callback);

}  // namespace device
}  // namespace omi
