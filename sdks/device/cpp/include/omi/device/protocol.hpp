#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace omi {
namespace device {

inline constexpr const char* kServiceUuid = "19b10000-e8f2-537e-4f6c-d104768a1214";
inline constexpr const char* kAudioDataUuid = "19b10001-e8f2-537e-4f6c-d104768a1214";
inline constexpr const char* kAudioCodecUuid = "19b10002-e8f2-537e-4f6c-d104768a1214";
inline constexpr const char* kBatteryServiceUuid = "0000180f-0000-1000-8000-00805f9b34fb";
inline constexpr const char* kBatteryLevelUuid = "00002a19-0000-1000-8000-00805f9b34fb";

inline constexpr std::size_t kPacketHeaderBytes = 3;
inline constexpr int kPcmSampleRateHz = 16000;
inline constexpr int kOpusFrameSamples = 960;
inline constexpr int kPcmChannels = 1;

enum class BleAudioCodec : std::uint8_t {
  Pcm16 = 0,
  Pcm8 = 1,
  Opus = 20,
  OpusFs320 = 21,
};

inline constexpr BleAudioCodec MapCodecId(std::uint8_t id) {
  switch (id) {
    case 0: return BleAudioCodec::Pcm16;
    case 1: return BleAudioCodec::Pcm8;
    case 20: return BleAudioCodec::Opus;
    case 21: return BleAudioCodec::OpusFs320;
    default: return static_cast<BleAudioCodec>(id);
  }
}

// Returns payload after the 3-byte header; empty if packet too short.
std::vector<std::uint8_t> StripPacketHeader(const std::uint8_t* data, std::size_t len);

}  // namespace device
}  // namespace omi
