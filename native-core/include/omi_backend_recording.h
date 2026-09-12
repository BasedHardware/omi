#ifndef OMI_BACKEND_RECORDING_H
#define OMI_BACKEND_RECORDING_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Shared recording journal policy (C ABI). Pure validation and matching rules
 * used by the Apple and Android journals. Keystore/keychain, filesystem, JSON,
 * and platform error types stay in the shims.
 */

#define OMI_BACKEND_RECORDING_MAX_CAPTURED_AT_MS 8640000000000000.0
#define OMI_BACKEND_RECORDING_MAX_TOTAL_BYTES 134217728ULL
#define OMI_BACKEND_RECORDING_MAX_FILES 64

/** 1 if value is a finite, non-negative, integral millisecond timestamp. */
int32_t omi_backend_recording_captured_at_valid(double value);

/**
 * 1 when both timestamps are absent, or both are present and equal.
 * Presence is explicit so absent never matches an explicit zero.
 */
int32_t omi_backend_recording_captured_at_equal(int32_t expected_present,
                                                double expected,
                                                int32_t actual_present,
                                                double actual);

/** 1 for 408, 429, and 5xx (retryable ownership refresh) statuses. */
int32_t omi_backend_recording_retryable_status(int32_t status);

/** 1 when both login and origin are non-empty and match pairwise. */
int32_t omi_backend_recording_same_context(const char* expected_login,
                                           const char* current_login,
                                           const char* expected_origin,
                                           const char* current_origin);

/** 1 when identifier is 1..128 chars and name is 1..256 chars. */
int32_t omi_backend_recording_remembered_identity(const char* identifier,
                                                  const char* name);

/** 1 when the ticket is current, ready, and the login is non-empty and equal. */
int32_t omi_backend_recording_remembered_current(uint64_t ticket,
                                                 uint64_t generation,
                                                 const char* expected_login,
                                                 const char* current_login,
                                                 int32_t ready);

/** 1 for a 1..256 char device id, optional <=256 char name, integer 0..255 codec. */
int32_t omi_backend_recording_device_valid(const char* device_id,
                                           int32_t name_present,
                                           const char* device_name, double codec);

/** 1 when total+extra fits the byte budget and creation stays under 64 files. */
int32_t omi_backend_recording_budget_ok(uint64_t total_bytes,
                                        uint64_t extra_bytes, int32_t creating,
                                        uint32_t file_count);

#ifdef __cplusplus
}
#endif

#endif /* OMI_BACKEND_RECORDING_H */
