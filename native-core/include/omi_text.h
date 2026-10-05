#ifndef OMI_TEXT_H
#define OMI_TEXT_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Scans UTF-8 with fatal-decoder rules (no overlongs, surrogates or scalars
 * above U+10FFFF). Writes into `out_complete` the length of the prefix made
 * of whole scalars; any remaining bytes are a truncated trailing sequence.
 * Returns 0 when the input is valid so far, -1 on an invalid sequence or
 * invalid arguments.
 */
int32_t omi_utf8_complete_prefix(const uint8_t* data, size_t length,
                                 size_t* out_complete);

/**
 * Copies `data` into `out` as valid UTF-8, replacing each maximal invalid
 * subpart with U+FFFD (the WHATWG / Unicode replacement policy).
 * `out_capacity` must be at least 3 * length. Returns 0 on success with the
 * byte count in `out_length`, -1 on invalid arguments.
 */
int32_t omi_utf8_lossy(const uint8_t* data, size_t length, uint8_t* out,
                       size_t out_capacity, size_t* out_length);

/**
 * Formats a finite double exactly as ECMAScript Number::toString does.
 * Returns the length written (excluding NUL), or -1 for non-finite values,
 * invalid arguments or insufficient capacity (32 bytes always suffice).
 */
int32_t omi_json_format_number(double value, char* out, size_t out_capacity);

/**
 * Returns 1 when `text` is a complete RFC 8259 JSON number, else 0.
 */
int32_t omi_json_number_valid(const char* text, size_t length);

#ifdef __cplusplus
}
#endif

#endif // OMI_TEXT_H
