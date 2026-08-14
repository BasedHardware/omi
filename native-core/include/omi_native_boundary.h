#ifndef OMI_NATIVE_BOUNDARY_H
#define OMI_NATIVE_BOUNDARY_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Status codes for packet normalization
#define OMI_STATUS_OK 0
#define OMI_STATUS_ERR_INVALID_PARAM -1
#define OMI_STATUS_ERR_SYNC_BYTES -2
#define OMI_STATUS_ERR_CHECKSUM -3
#define OMI_STATUS_ERR_BUFFER_OVERFLOW -4

/**
 * Calculates CRC32 checksum for raw packet payload.
 */
uint32_t omi_calculate_packet_checksum(const uint8_t* data, size_t length);

/**
 * Normalizes a framed packet (sync 0xAA 0x55 + payload + 4-byte CRC32 big endian).
 * Extracts payload into out_data and returns status code.
 */
int32_t omi_normalize_packet(
    const uint8_t* raw_data,
    size_t raw_len,
    uint8_t* out_data,
    size_t max_out_len,
    size_t* out_len
);

/**
 * Queries native host hardware capability JSON string.
 */
int32_t omi_get_native_capabilities(char* out_buf, size_t max_buf_len);

#ifdef __cplusplus
}
#endif

#endif // OMI_NATIVE_BOUNDARY_H
