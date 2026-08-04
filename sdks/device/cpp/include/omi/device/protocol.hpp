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

// Returns payload after the 3-byte header; empty if packet too short.
std::vector<std::uint8_t> StripPacketHeader(const std::uint8_t* data, std::size_t len);

}  // namespace device
}  // namespace omi
