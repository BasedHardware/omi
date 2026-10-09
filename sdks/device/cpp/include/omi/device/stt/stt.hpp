#pragma once

#include <cctype>
#include <string>

namespace omi {
namespace device {
namespace stt {

enum class Engine { Deepgram, Whisper, Parakeet };

inline std::string ParakeetWsUrl(std::string api_url, int sample_rate = 16000) {
  const auto fragment = api_url.find('#');
  if (fragment != std::string::npos) api_url.erase(fragment);
  std::string query;
  const auto query_start = api_url.find('?');
  if (query_start != std::string::npos) {
    query = api_url.substr(query_start + 1);
    api_url.erase(query_start);
  }
  while (!api_url.empty() && api_url.back() == '/') api_url.pop_back();
  auto replace_prefix = [&](const std::string& from, const std::string& to) {
    if (api_url.rfind(from, 0) == 0) {
      api_url = to + api_url.substr(from.size());
    }
  };
  replace_prefix("https://", "wss://");
  replace_prefix("http://", "ws://");
  std::string result = api_url + "/v3/stream?";
  for (std::size_t start = 0; start < query.size();) {
    const auto end = query.find('&', start);
    const auto param = query.substr(start, end == std::string::npos ? end : end - start);
    auto key = param.substr(0, param.find('='));
    for (std::size_t i = 0; i + 2 < key.size(); ++i) {
      if (key[i] == '%' && std::isxdigit(static_cast<unsigned char>(key[i + 1])) &&
          std::isxdigit(static_cast<unsigned char>(key[i + 2]))) {
        key.replace(i, 3, 1, static_cast<char>(std::stoi(key.substr(i + 1, 2), nullptr, 16)));
      }
    }
    // Preserve encoded query values while replacing every stale sample rate.
    if (!param.empty() && key != "sample_rate") {
      result += param + "&";
    }
    if (end == std::string::npos) break;
    start = end + 1;
  }
  return result + "sample_rate=" + std::to_string(sample_rate);
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
// BLE is injected rather than gated: implement omi::device::BleBackend against
// CoreBluetooth/WinRT/BlueZ and install it with SetBleBackend(). See README.md.

}  // namespace stt
}  // namespace device
}  // namespace omi
