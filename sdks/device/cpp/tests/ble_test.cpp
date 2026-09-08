// Hermetic tests for the injectable BLE surface: no adapter, no network.
#include "omi/device/ble.hpp"
#include "omi/device/protocol.hpp"

#include <cstdio>
#include <cstdlib>
#include <memory>
#include <string>
#include <vector>

namespace {

int g_failures = 0;

void Check(bool ok, const char* what) {
  if (!ok) {
    std::fprintf(stderr, "FAIL: %s\n", what);
    ++g_failures;
  }
}

// Records what the SDK asked the platform stack to do, and replays packets.
class FakeBackend : public omi::device::BleBackend {
 public:
  explicit FakeBackend(std::vector<std::vector<std::uint8_t>> packets)
      : packets_(std::move(packets)) {}

  std::vector<omi::device::BleDevice> Scan(int timeout_ms) override {
    scan_timeout_ms = timeout_ms;
    return {omi::device::BleDevice{"AA:BB:CC:DD:EE:FF", "Omi", -42}};
  }

  void Notify(const std::string& device_id, const std::string& service_uuid,
              const std::string& characteristic_uuid,
              omi::device::PacketCallback on_packet) override {
    notify_device_id = device_id;
    notify_service_uuid = service_uuid;
    notify_characteristic_uuid = characteristic_uuid;
    for (const auto& packet : packets_) {
      on_packet(packet);
    }
  }

  int scan_timeout_ms = -1;
  std::string notify_device_id;
  std::string notify_service_uuid;
  std::string notify_characteristic_uuid;

 private:
  std::vector<std::vector<std::uint8_t>> packets_;
};

template <typename Fn>
bool ThrowsBleDisabled(Fn fn) {
  try {
    fn();
  } catch (const omi::device::BleDisabled&) {
    return true;
  } catch (...) {
    return false;
  }
  return false;
}

// Default build links no BLE stack: every entry point must refuse, not dial out.
void TestDisabledWithoutBackend() {
  omi::device::SetBleBackend(nullptr);

  Check(omi::device::GetBleBackend() == nullptr, "GetBleBackend is null by default");
  Check(ThrowsBleDisabled([] { omi::device::Scan(10); }), "Scan throws BleDisabled");
  Check(ThrowsBleDisabled([] { omi::device::Listen("id", [](const std::vector<std::uint8_t>&) {}); }),
        "Listen throws BleDisabled");
  Check(ThrowsBleDisabled(
            [] { omi::device::ListenPayload("id", [](const std::vector<std::uint8_t>&) {}); }),
        "ListenPayload throws BleDisabled");
}

void TestScanUsesBackend() {
  auto backend = std::make_shared<FakeBackend>(std::vector<std::vector<std::uint8_t>>{});
  omi::device::SetBleBackend(backend);

  auto devices = omi::device::Scan(1234);
  Check(devices.size() == 1, "Scan returns backend devices");
  Check(devices[0].id == "AA:BB:CC:DD:EE:FF", "Scan preserves device id");
  Check(devices[0].name == "Omi", "Scan preserves device name");
  Check(devices[0].rssi == -42, "Scan preserves rssi");
  Check(backend->scan_timeout_ms == 1234, "Scan forwards timeout");

  omi::device::Scan(-5);
  Check(backend->scan_timeout_ms == 0, "Scan clamps a negative timeout to 0");

  omi::device::SetBleBackend(nullptr);
}

void TestListenSubscribesToAudioCharacteristic() {
  const std::vector<std::uint8_t> packet{0x01, 0x00, 0x00, 0xAA, 0xBB};
  auto backend = std::make_shared<FakeBackend>(std::vector<std::vector<std::uint8_t>>{packet});
  omi::device::SetBleBackend(backend);

  std::vector<std::vector<std::uint8_t>> got;
  omi::device::Listen("dev-1", [&](const std::vector<std::uint8_t>& bytes) { got.push_back(bytes); });

  Check(backend->notify_device_id == "dev-1", "Listen forwards the device id");
  Check(backend->notify_service_uuid == std::string(omi::device::kServiceUuid),
        "Listen subscribes on kServiceUuid");
  Check(backend->notify_characteristic_uuid == std::string(omi::device::kAudioDataUuid),
        "Listen subscribes to kAudioDataUuid");
  Check(got.size() == 1 && got[0] == packet, "Listen delivers raw packets with the header intact");

  omi::device::SetBleBackend(nullptr);
}

void TestListenPayloadStripsHeader() {
  const std::vector<std::uint8_t> full{0x01, 0x00, 0x00, 0xAA, 0xBB};
  const std::vector<std::uint8_t> header_only{0x01, 0x00, 0x00};
  const std::vector<std::uint8_t> too_short{0x01, 0x00};
  auto backend = std::make_shared<FakeBackend>(
      std::vector<std::vector<std::uint8_t>>{full, header_only, too_short});
  omi::device::SetBleBackend(backend);

  std::vector<std::vector<std::uint8_t>> got;
  omi::device::ListenPayload("dev-1",
                             [&](const std::vector<std::uint8_t>& bytes) { got.push_back(bytes); });

  Check(got.size() == 1, "ListenPayload drops header-only and short packets");
  Check(got.size() == 1 && got[0] == std::vector<std::uint8_t>({0xAA, 0xBB}),
        "ListenPayload strips the 3-byte header");

  omi::device::SetBleBackend(nullptr);
}

void TestEmptyCallbackRejected() {
  auto backend = std::make_shared<FakeBackend>(std::vector<std::vector<std::uint8_t>>{});
  omi::device::SetBleBackend(backend);

  bool listen_threw = false;
  try {
    omi::device::Listen("dev-1", nullptr);
  } catch (const std::invalid_argument&) {
    listen_threw = true;
  }
  Check(listen_threw, "Listen rejects an empty callback");

  bool payload_threw = false;
  try {
    omi::device::ListenPayload("dev-1", nullptr);
  } catch (const std::invalid_argument&) {
    payload_threw = true;
  }
  Check(payload_threw, "ListenPayload rejects an empty callback");

  omi::device::SetBleBackend(nullptr);
}

void TestStripPacketHeader() {
  const std::vector<std::uint8_t> full{0x01, 0x00, 0x00, 0xAA, 0xBB};
  auto payload = omi::device::StripPacketHeader(full.data(), full.size());
  Check(payload == std::vector<std::uint8_t>({0xAA, 0xBB}), "StripPacketHeader drops 3 bytes");
  Check(omi::device::StripPacketHeader(nullptr, 8).empty(), "StripPacketHeader tolerates nullptr");
  Check(omi::device::StripPacketHeader(full.data(), omi::device::kPacketHeaderBytes).empty(),
        "StripPacketHeader returns empty for a header-only packet");
}

}  // namespace

int main() {
  TestDisabledWithoutBackend();
  TestScanUsesBackend();
  TestListenSubscribesToAudioCharacteristic();
  TestListenPayloadStripsHeader();
  TestEmptyCallbackRejected();
  TestStripPacketHeader();

  if (g_failures != 0) {
    std::fprintf(stderr, "%d check(s) failed\n", g_failures);
    return EXIT_FAILURE;
  }
  std::printf("all omi_device checks passed\n");
  return EXIT_SUCCESS;
}
