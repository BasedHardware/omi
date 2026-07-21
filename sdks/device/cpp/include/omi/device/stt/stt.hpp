#pragma once

#include <string>

namespace omi {
namespace device {
namespace stt {

enum class Engine { Deepgram, Whisper, Parakeet };

inline std::string ParakeetWsUrl(std::string api_url, int sample_rate = 16000) {
  while (!api_url.empty() && api_url.back() == '/') api_url.pop_back();
  auto replace_prefix = [&](const std::string& from, const std::string& to) {
    if (api_url.rfind(from, 0) == 0) {
      api_url = to + api_url.substr(from.size());
    }
  };
  replace_prefix("https://", "wss://");
  replace_prefix("http://", "ws://");
  return api_url + "/v3/stream?sample_rate=" + std::to_string(sample_rate);
}

inline std::string DeepgramWsUrl(int sample_rate = 16000) {
  return "wss://api.deepgram.com/v1/listen?punctuate=true&model=nova&language=en-US"
         "&encoding=linear16&sample_rate=" +
         std::to_string(sample_rate) + "&channels=1";
}

// Streaming clients are feature-gated:
//  - define OMI_STT_DEEPGRAM and link a WS stack to enable Deepgram
//  - define OMI_STT_PARAKEET similarly
//  - define OMI_STT_WHISPER and inject a local runner for Whisper
// BLE stacks similarly gate with OMI_DEVICE_BLE (CoreBluetooth/WinRT/Android JNI).

}  // namespace stt
}  // namespace device
}  // namespace omi
