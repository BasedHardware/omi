#include "omi_native_boundary.h"
#include <cstdio>
#include <cstring>

uint32_t omi_calculate_packet_checksum(const uint8_t* data, size_t length) {
    if (data == nullptr || length == 0) {
        return 0;
    }
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < length; ++i) {
        crc ^= data[i];
        for (int j = 0; j < 8; ++j) {
            crc = (crc >> 1) ^ (crc & 1 ? 0xEDB88320U : 0U);
        }
    }
    return crc ^ 0xFFFFFFFF;
}

int32_t omi_normalize_packet(
    const uint8_t* raw_data,
    size_t raw_len,
    uint8_t* out_data,
    size_t max_out_len,
    size_t* out_len
) {
    if (raw_data == nullptr || out_data == nullptr || out_len == nullptr) {
        return OMI_STATUS_ERR_INVALID_PARAM;
    }

    // Minimum framed packet size: 2 sync bytes + 0 payload + 4 checksum bytes = 6 bytes
    if (raw_len < 6) {
        return OMI_STATUS_ERR_INVALID_PARAM;
    }

    // Check framing sync header: 0xAA 0x55
    if (raw_data[0] != 0xAA || raw_data[1] != 0x55) {
        return OMI_STATUS_ERR_SYNC_BYTES;
    }

    size_t payload_len = raw_len - 6;
    if (payload_len > max_out_len) {
        return OMI_STATUS_ERR_BUFFER_OVERFLOW;
    }

    // Extract expected CRC32 (big-endian)
    uint32_t expected_crc = ((uint32_t)raw_data[raw_len - 4] << 24) |
                             ((uint32_t)raw_data[raw_len - 3] << 16) |
                             ((uint32_t)raw_data[raw_len - 2] << 8)  |
                             ((uint32_t)raw_data[raw_len - 1]);

    const uint8_t* payload_ptr = raw_data + 2;
    uint32_t computed_crc = omi_calculate_packet_checksum(payload_ptr, payload_len);

    if (computed_crc != expected_crc) {
        return OMI_STATUS_ERR_CHECKSUM;
    }

    if (payload_len > 0) {
        std::memcpy(out_data, payload_ptr, payload_len);
    }
    *out_len = payload_len;

    return OMI_STATUS_OK;
}

int32_t omi_get_native_capabilities(char* out_buf, size_t max_buf_len) {
    if (out_buf == nullptr) {
        return OMI_STATUS_ERR_INVALID_PARAM;
    }
    const char* caps = "{\"simd\":true,\"abi_version\":1,\"max_packet_bytes\":4096}";
    size_t len = std::strlen(caps);
    if (len + 1 > max_buf_len) {
        return OMI_STATUS_ERR_BUFFER_OVERFLOW;
    }
    std::memcpy(out_buf, caps, len + 1);
    return OMI_STATUS_OK;
}
