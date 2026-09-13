#ifndef DEVICE_NAME_H
#define DEVICE_NAME_H

/*
 * Pure device-name policy shared by the BLE write handler, the settings
 * loader, and the advertising builder. No Zephyr dependencies so the rules
 * can be executed on the host (tests/test_device_name.c).
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/*
 * Longest accepted name, in UTF-8 bytes. 20 is the ATT payload of a single
 * Write Request at the default 23-byte MTU, so a rename never needs the
 * prepare/execute long-write procedure regardless of what MTU the phone
 * negotiated. It also fits the 31-byte scan response next to the 4-byte DIS
 * UUID16 entry: 4 + 2 (name AD header) + 20 = 26 <= 31.
 */
#define OMI_DEVICE_NAME_MAX_LEN 20
#define OMI_DEVICE_NAME_SCAN_RSP_BUDGET (31 - 4 - 2)

/*
 * Bytes of the name that fit in the primary advertisement next to the flags
 * (3 bytes) and the 128-bit audio service UUID (18 bytes):
 * 31 - 3 - 18 - 2 (name AD header) = 8. Longer names are shortened here and
 * sent complete in the scan response.
 */
#define OMI_DEVICE_NAME_ADV_MAX_LEN 8

/* Returns the byte length of the UTF-8 sequence that starts with lead, or 0 if lead is not a valid lead byte. */
static inline size_t omi_device_name_utf8_seq_len(uint8_t lead)
{
    if (lead < 0x80) {
        return 1;
    }
    if ((lead & 0xE0) == 0xC0) {
        return lead >= 0xC2 ? 2 : 0; /* 0xC0/0xC1 are overlong encodings */
    }
    if ((lead & 0xF0) == 0xE0) {
        return 3;
    }
    if ((lead & 0xF8) == 0xF0) {
        return lead <= 0xF4 ? 4 : 0; /* above U+10FFFF */
    }
    return 0;
}

/*
 * A name is valid when it is 1..OMI_DEVICE_NAME_MAX_LEN bytes of well-formed
 * UTF-8, contains no ASCII control characters (including NUL and DEL) and
 * does not start or end with a space. Everything else is rejected so the
 * device never advertises a name the app could not have produced.
 */
static inline bool omi_device_name_is_valid(const uint8_t *buf, size_t len)
{
    if (buf == NULL || len == 0 || len > OMI_DEVICE_NAME_MAX_LEN) {
        return false;
    }
    if (buf[0] == ' ' || buf[len - 1] == ' ') {
        return false;
    }

    size_t i = 0;
    while (i < len) {
        uint8_t lead = buf[i];
        size_t seq = omi_device_name_utf8_seq_len(lead);
        if (seq == 0 || i + seq > len) {
            return false;
        }
        if (seq == 1) {
            if (lead < 0x20 || lead == 0x7F) {
                return false;
            }
        } else {
            for (size_t k = 1; k < seq; k++) {
                if ((buf[i + k] & 0xC0) != 0x80) {
                    return false;
                }
            }
            /* Reject surrogates (U+D800..U+DFFF), which are invalid in UTF-8. */
            if (seq == 3 && lead == 0xED && buf[i + 1] >= 0xA0) {
                return false;
            }
        }
        i += seq;
    }
    return true;
}

/*
 * Longest prefix of a valid UTF-8 name that is at most max_len bytes and does
 * not split a multi-byte character. Used for the shortened advertised name.
 */
static inline size_t omi_device_name_utf8_prefix_len(const uint8_t *buf, size_t len, size_t max_len)
{
    if (buf == NULL || len <= max_len) {
        return len;
    }
    size_t cut = max_len;
    while (cut > 0 && (buf[cut] & 0xC0) == 0x80) {
        cut--;
    }
    return cut;
}

#endif // DEVICE_NAME_H
