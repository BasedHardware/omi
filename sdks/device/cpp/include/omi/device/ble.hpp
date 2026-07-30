#pragma once

#include "omi/device/protocol.hpp"

#include <cstdint>
#include <functional>
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

// Requires OMI_DEVICE_BLE=ON and SimpleBLE linked.
std::vector<BleDevice> Scan(int timeout_ms = 5000);

// Connect to device_id, notify on kAudioDataUuid, invoke callback with raw bytes.
// Blocks until disconnect. Uses kServiceUuid / kAudioDataUuid from protocol.hpp.
void Listen(const std::string& device_id, PacketCallback callback);

// Same as Listen but strips the 3-byte Omi packet header before callback.
void ListenPayload(const std::string& device_id, PacketCallback callback);

}  // namespace device
}  // namespace omi
