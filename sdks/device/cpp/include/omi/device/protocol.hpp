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
// Decode buffer bound for opus_decode, not the wire frame size (160 or 320 samples).
inline constexpr int kOpusFrameSamples = 960;
inline constexpr int kPcmChannels = 1;

// First byte of the audio codec characteristic. See sdks/device/PROTOCOL.md.
inline constexpr std::uint8_t kCodecPcm16 = 0;
inline constexpr std::uint8_t kCodecPcm8 = 1;
// 160-sample frames @ 100 fps (DevKit firmware).
inline constexpr std::uint8_t kCodecOpus = 20;
// 320-sample frames @ 50 fps (Omi CV1 firmware).
inline constexpr std::uint8_t kCodecOpusFs320 = 21;

// Returns payload after the 3-byte header; empty if packet too short.
std::vector<std::uint8_t> StripPacketHeader(const std::uint8_t* data, std::size_t len);

}  // namespace device
}  // namespace omi
