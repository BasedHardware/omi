#include "omi/device/ble.hpp"

#include <chrono>
#include <stdexcept>
#include <thread>

#include <simpleble/SimpleBLE.h>

namespace omi {
namespace device {
namespace {

SimpleBLE::Adapter GetAdapter() {
  if (!SimpleBLE::Adapter::bluetooth_enabled()) {
    throw std::runtime_error("Bluetooth is disabled");
  }
  auto adapters = SimpleBLE::Adapter::get_adapters();
  if (adapters.empty()) {
    throw std::runtime_error("No Bluetooth adapters found");
  }
  return adapters.front();
}

SimpleBLE::Peripheral FindPeripheral(SimpleBLE::Adapter& adapter, const std::string& device_id) {
  adapter.scan_for(2000);
  for (auto& p : adapter.scan_get_results()) {
    if (p.address() == device_id || p.identifier() == device_id) {
      return p;
    }
  }
  // Also check already-connected/paired lists when available.
  for (auto& p : adapter.get_paired_peripherals()) {
    if (p.address() == device_id || p.identifier() == device_id) {
      return p;
    }
  }
  throw std::runtime_error("BLE device not found: " + device_id);
}

}  // namespace

std::vector<BleDevice> Scan(int timeout_ms) {
  auto adapter = GetAdapter();
  adapter.scan_for(timeout_ms < 0 ? 0 : timeout_ms);

  std::vector<BleDevice> out;
  for (auto& p : adapter.scan_get_results()) {
    out.push_back(BleDevice{p.address(), p.identifier(), static_cast<int>(p.rssi())});
  }
  return out;
}

void Listen(const std::string& device_id, PacketCallback callback) {
  if (!callback) {
    throw std::invalid_argument("Listen callback is empty");
  }
  auto adapter = GetAdapter();
  auto peripheral = FindPeripheral(adapter, device_id);
  peripheral.connect();

  bool alive = true;
  peripheral.set_callback_on_disconnected([&]() { alive = false; });

  peripheral.notify(kServiceUuid, kAudioDataUuid, [&](SimpleBLE::ByteArray bytes) {
    std::vector<std::uint8_t> raw(bytes.begin(), bytes.end());
    callback(raw);
  });

  while (alive && peripheral.is_connected()) {
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
  }

  if (peripheral.is_connected()) {
    try {
      peripheral.unsubscribe(kServiceUuid, kAudioDataUuid);
    } catch (...) {
    }
    peripheral.disconnect();
  }
}

void ListenPayload(const std::string& device_id, PacketCallback callback) {
  if (!callback) {
    throw std::invalid_argument("ListenPayload callback is empty");
  }
  Listen(device_id, [callback = std::move(callback)](const std::vector<std::uint8_t>& packet) {
    if (packet.size() <= kPacketHeaderBytes) {
      return;
    }
    auto payload = StripPacketHeader(packet.data(), packet.size());
    if (!payload.empty()) {
      callback(payload);
    }
  });
}

}  // namespace device
}  // namespace omi
