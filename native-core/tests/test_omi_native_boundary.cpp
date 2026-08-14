#include "omi_native_boundary.h"
#include <iostream>
#include <vector>
#include <string>
#include <cstring>
#include <cassert>

static int g_tests_run = 0;
static int g_tests_failed = 0;

#define TEST_ASSERT(cond, msg) \
    do { \
        g_tests_run++; \
        if (!(cond)) { \
            std::cerr << "  [FAIL] " << msg << " (line " << __LINE__ << ")\n"; \
            g_tests_failed++; \
        } else { \
            std::cout << "  [PASS] " << msg << "\n"; \
        } \
    } while(0)

void test_checksum_calculation() {
    std::cout << "Running test_checksum_calculation...\n";
    // Null or empty
    TEST_ASSERT(omi_calculate_packet_checksum(nullptr, 0) == 0, "Null pointer returns 0 checksum");

    // Known payload
    uint8_t data[] = {0x01, 0x02, 0x03, 0x04};
    uint32_t crc = omi_calculate_packet_checksum(data, 4);
    TEST_ASSERT(crc != 0, "Checksum calculation produces non-zero CRC32");

    // Determinism
    uint32_t crc2 = omi_calculate_packet_checksum(data, 4);
    TEST_ASSERT(crc == crc2, "Checksum is deterministic for identical input");
}

void test_packet_normalization_success() {
    std::cout << "Running test_packet_normalization_success...\n";
    uint8_t payload[] = {0xDE, 0xAD, 0xBE, 0xEF};
    size_t payload_len = 4;
    uint32_t expected_crc = omi_calculate_packet_checksum(payload, payload_len);

    // Frame packet: sync (2 bytes 0xAA, 0x55) + payload (4 bytes) + CRC32 (4 bytes big endian)
    std::vector<uint8_t> frame = {0xAA, 0x55, 0xDE, 0xAD, 0xBE, 0xEF};
    frame.push_back((expected_crc >> 24) & 0xFF);
    frame.push_back((expected_crc >> 16) & 0xFF);
    frame.push_back((expected_crc >> 8) & 0xFF);
    frame.push_back(expected_crc & 0xFF);

    uint8_t out_buf[16] = {0};
    size_t out_len = 0;
    int32_t status = omi_normalize_packet(frame.data(), frame.size(), out_buf, sizeof(out_buf), &out_len);

    TEST_ASSERT(status == OMI_STATUS_OK, "Packet normalization returns STATUS_OK");
    TEST_ASSERT(out_len == payload_len, "Extracted payload length matches original payload");
    TEST_ASSERT(memcmp(out_buf, payload, payload_len) == 0, "Extracted payload content matches original payload");
}

void test_packet_normalization_errors() {
    std::cout << "Running test_packet_normalization_errors...\n";
    // Bad sync
    uint8_t bad_sync[] = {0x00, 0x00, 0x01, 0x02, 0x00, 0x00, 0x00, 0x00};
    uint8_t out_buf[16];
    size_t out_len = 0;
    int32_t status_sync = omi_normalize_packet(bad_sync, sizeof(bad_sync), out_buf, sizeof(out_buf), &out_len);
    TEST_ASSERT(status_sync == OMI_STATUS_ERR_SYNC_BYTES, "Invalid sync header returns OMI_STATUS_ERR_SYNC_BYTES");

    // Bad CRC
    uint8_t bad_crc_frame[] = {0xAA, 0x55, 0x01, 0x02, 0x99, 0x99, 0x99, 0x99};
    int32_t status_crc = omi_normalize_packet(bad_crc_frame, sizeof(bad_crc_frame), out_buf, sizeof(out_buf), &out_len);
    TEST_ASSERT(status_crc == OMI_STATUS_ERR_CHECKSUM, "Checksum mismatch returns OMI_STATUS_ERR_CHECKSUM");

    // Buffer overflow
    uint8_t payload[] = {0x11, 0x22, 0x33};
    uint32_t crc = omi_calculate_packet_checksum(payload, 3);
    std::vector<uint8_t> frame = {0xAA, 0x55, 0x11, 0x22, 0x33};
    frame.push_back((crc >> 24) & 0xFF);
    frame.push_back((crc >> 16) & 0xFF);
    frame.push_back((crc >> 8) & 0xFF);
    frame.push_back(crc & 0xFF);

    uint8_t tiny_buf[1]; // too small for 3 byte payload
    int32_t status_overflow = omi_normalize_packet(frame.data(), frame.size(), tiny_buf, sizeof(tiny_buf), &out_len);
    TEST_ASSERT(status_overflow == OMI_STATUS_ERR_BUFFER_OVERFLOW, "Insufficient out_buf returns OMI_STATUS_ERR_BUFFER_OVERFLOW");
}

void test_native_capabilities() {
    std::cout << "Running test_native_capabilities...\n";
    char buf[256] = {0};
    int32_t status = omi_get_native_capabilities(buf, sizeof(buf));
    TEST_ASSERT(status == OMI_STATUS_OK, "get_native_capabilities returns STATUS_OK");
    std::string cap_str(buf);
    TEST_ASSERT(cap_str.find("abi_version") != std::string::npos, "Capabilities string includes abi_version");
    TEST_ASSERT(cap_str.find("simd") != std::string::npos, "Capabilities string includes simd field");

    // Small buffer test
    char small_buf[5] = {0};
    int32_t overflow_status = omi_get_native_capabilities(small_buf, sizeof(small_buf));
    TEST_ASSERT(overflow_status == OMI_STATUS_ERR_BUFFER_OVERFLOW, "Small buffer returns OMI_STATUS_ERR_BUFFER_OVERFLOW");
}

int main() {
    std::cout << "=== Running Omi C++ Native Boundary Host Tests ===\n";
    test_checksum_calculation();
    test_packet_normalization_success();
    test_packet_normalization_errors();
    test_native_capabilities();

    std::cout << "\nTest Summary: " << g_tests_run << " run, " << g_tests_failed << " failed.\n";
    return (g_tests_failed == 0) ? 0 : 1;
}
