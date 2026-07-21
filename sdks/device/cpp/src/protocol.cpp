#include "omi/device/protocol.hpp"

namespace omi {
namespace device {

std::vector<std::uint8_t> StripPacketHeader(const std::uint8_t* data, std::size_t len) {
  if (data == nullptr || len <= kPacketHeaderBytes) {
    return {};
  }
  return std::vector<std::uint8_t>(data + kPacketHeaderBytes, data + len);
}

}  // namespace device
}  // namespace omi
