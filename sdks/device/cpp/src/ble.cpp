#include "omi/device/ble.hpp"

#include <mutex>
#include <stdexcept>
#include <utility>

namespace omi {
namespace device {
namespace {

std::mutex& BackendMutex() {
  static std::mutex mu;
  return mu;
}

std::shared_ptr<BleBackend>& BackendSlot() {
  static std::shared_ptr<BleBackend> backend;
  return backend;
}

std::shared_ptr<BleBackend> RequireBackend() {
  auto backend = GetBleBackend();
  if (!backend) {
    throw BleDisabled();
  }
  return backend;
}

}  // namespace

void SetBleBackend(std::shared_ptr<BleBackend> backend) {
  std::lock_guard<std::mutex> lock(BackendMutex());
  BackendSlot() = std::move(backend);
}

std::shared_ptr<BleBackend> GetBleBackend() {
  std::lock_guard<std::mutex> lock(BackendMutex());
  return BackendSlot();
}

std::vector<BleDevice> Scan(int timeout_ms) {
  return RequireBackend()->Scan(timeout_ms < 0 ? 0 : timeout_ms);
}

void Listen(const std::string& device_id, PacketCallback callback) {
  if (!callback) {
    throw std::invalid_argument("Listen callback is empty");
  }
  RequireBackend()->Notify(device_id, kServiceUuid, kAudioDataUuid, std::move(callback));
}

void ListenPayload(const std::string& device_id, PacketCallback callback) {
  if (!callback) {
    throw std::invalid_argument("ListenPayload callback is empty");
  }
  Listen(device_id, [callback = std::move(callback)](const std::vector<std::uint8_t>& packet) {
    auto payload = StripPacketHeader(packet.data(), packet.size());
    if (!payload.empty()) {
      callback(payload);
    }
  });
}

}  // namespace device
}  // namespace omi
