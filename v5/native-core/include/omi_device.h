#ifndef OMI_DEVICE_H
#define OMI_DEVICE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Capture stage codes (mirrors CaptureStage in OmiKit/Devices).
#define OMI_DEVICE_STAGE_IDLE 0
#define OMI_DEVICE_STAGE_WAITING 1
#define OMI_DEVICE_STAGE_ACTIVE 2
#define OMI_DEVICE_STAGE_COMPLETED 3
#define OMI_DEVICE_STAGE_FAILED 4

// Assembler classification outcomes.
#define OMI_DEVICE_PACKET_ACCEPTED 0
#define OMI_DEVICE_PACKET_DUPLICATE 1
#define OMI_DEVICE_PACKET_SHORT_FRAME 2
#define OMI_DEVICE_PACKET_CODEC_INVALID 3

// Battery history persistence rule: at most one unchanged reading per hour.
#define OMI_DEVICE_BATTERY_HISTORY_MIN_INTERVAL_MS ((int64_t)60 * 60 * 1000)

// String-out convention: every function writing into (out, out_cap) returns
// the number of bytes written excluding the NUL terminator (>= 0) on success,
// or OMI_STATUS_ERR_INVALID_PARAM (-1) when the input is absent/invalid or
// the buffer is too small. An empty result is success with 0 bytes written.

/**
 * True when the manufacturer-specific advertisement data carries the PLAUD
 * id (93, little-endian) followed by the NotePin payload (04 56 CF 00).
 */
int omi_device_is_note_pin_advertisement(const uint8_t* data, size_t len);

/**
 * Scan-time display name: the trimmed advertised local name, else the
 * trimmed cached name, else "NotePin" when the advertisement carries the
 * NotePin manufacturer payload, else the empty string.
 */
int omi_device_discovered_name(
    const char* advertised_local_name,
    const char* cached_name,
    const uint8_t* manufacturer_data,
    size_t manufacturer_data_len,
    char* out,
    size_t out_cap
);

/**
 * Discovery filter: true when the (case-insensitive) name contains "omi"
 * or "notepin".
 */
int omi_device_is_omi_like(const char* name);

/**
 * Battery persistence rule: persist when there is no previous reading, the
 * level changed, or at least one hour passed since the previous reading.
 */
int omi_device_should_persist_battery_reading(
    int32_t previous_level,
    int has_previous_level,
    int64_t previous_timestamp_ms,
    int has_previous_timestamp_ms,
    int32_t level,
    int64_t now_ms
);

/**
 * Device Information characteristic parser: trims ASCII whitespace, rejects
 * empty results, control bytes (< 0x20 or 0x7F), and invalid UTF-8; writes
 * the validated text otherwise.
 */
int omi_device_characteristic_text(
    const uint8_t* bytes,
    size_t len,
    char* out,
    size_t out_cap
);

// -----------------------------------------------------------------------
// Audio packet assembler: sequence-index dedupe over the shared codec.
// Raw notification layout: [seqLo, seqHi, 0xAA, 0x55, payload..., crc32 be].
// -----------------------------------------------------------------------

void* omi_device_assembler_create(void);
void omi_device_assembler_destroy(void* assembler);

/** Clears the sequence baseline (used when a capture opens). */
void omi_device_assembler_reset(void* assembler);

/**
 * Classifies one raw audio notification. On OMI_DEVICE_PACKET_ACCEPTED the
 * normalized payload is written to (out_payload, out_cap) with its length in
 * *out_payload_len and the sequence index in *out_index; otherwise
 * *out_kind carries DUPLICATE / SHORT_FRAME / CODEC_INVALID and, for
 * CODEC_INVALID, *out_codec_status carries the OMI_STATUS_* code from
 * omi_normalize_packet. Returns *out_kind for convenience; -1 on NULL
 * assembler.
 */
int32_t omi_device_assembler_classify(
    void* assembler,
    const uint8_t* raw,
    size_t raw_len,
    uint16_t* out_index,
    uint8_t* out_payload,
    size_t out_cap,
    size_t* out_payload_len,
    int32_t* out_codec_status
);

// -----------------------------------------------------------------------
// Capture state machine: open → waiting → active → (handoff | fail).
// -----------------------------------------------------------------------

void* omi_device_capture_create(void);
void omi_device_capture_destroy(void* machine);

/** Current OMI_DEVICE_STAGE_* code. */
int32_t omi_device_capture_stage(void* machine);

/** True while the stage is WAITING or ACTIVE. */
int omi_device_capture_is_capturing(void* machine);

/** Opens (or reopens) a capture; resets the batch and sequence baseline.
 *  Returns OMI_STATUS_OK, or OMI_STATUS_ERR_INVALID_PARAM for an empty
 *  device id. */
int omi_device_capture_open(
    void* machine,
    const char* device_id,
    const char* device_name,
    int32_t codec,
    int64_t now_ms
);

/**
 * Feeds one raw audio notification through the assembler while capturing.
 * Returns 1 with *out_index set when the packet was accepted into the batch,
 * 0 when it was rejected (duplicate / short frame / codec invalid / empty
 * payload / not capturing), -1 on NULL machine.
 */
int omi_device_capture_ingest(
    void* machine,
    const uint8_t* raw,
    size_t raw_len,
    int64_t received_at_ms,
    uint16_t* out_index
);

/** Marks the capture failed when it was still capturing (terminal). */
void omi_device_capture_fail(void* machine);

/**
 * Performs the journal handoff. Returns 1 when a nonempty batch was handed
 * off (batch retained for packet_at reads; *out_started_at_ms,
 * *out_ended_at_ms, *out_byte_count filled), 0 when the capture was not
 * capturing (no state change) or had no audio (stage advances to COMPLETED,
 * journal stays uncreated), -1 on NULL machine.
 */
int omi_device_capture_handoff(
    void* machine,
    int64_t now_ms,
    int64_t* out_started_at_ms,
    int64_t* out_ended_at_ms,
    size_t* out_byte_count
);

/** Batch size for the last successful handoff (0 otherwise). */
size_t omi_device_capture_packet_count(void* machine);

/** Size of the live (pre-handoff) batch and its byte count. */
size_t omi_device_capture_batch_count(void* machine);
size_t omi_device_capture_batch_byte_count(void* machine);

/** Open time of the current capture (0 when none). */
int64_t omi_device_capture_started_at_ms(void* machine);

/**
 * Copies one handed-off packet. Returns OMI_STATUS_OK, or
 * OMI_STATUS_ERR_INVALID_PARAM when out of range or the buffer is too small.
 */
int omi_device_capture_packet_at(
    void* machine,
    size_t position,
    uint16_t* out_index,
    uint8_t* out_payload,
    size_t out_cap,
    size_t* out_payload_len,
    int64_t* out_received_at_ms
);

/** Identity of the open capture ("" when none). */
int omi_device_capture_device_id(void* machine, char* out, size_t out_cap);

/** Device name of the open capture; -1 when absent. */
int omi_device_capture_device_name(void* machine, char* out, size_t out_cap);

/** Codec of the open capture (0 when none). */
int32_t omi_device_capture_codec(void* machine);

#ifdef __cplusplus
}
#endif

#endif // OMI_DEVICE_H
