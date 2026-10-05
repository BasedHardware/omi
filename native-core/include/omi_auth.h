#ifndef OMI_AUTH_H
#define OMI_AUTH_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define OMI_AUTH_SHA256_LENGTH 32

/**
 * SHA-256 of `length` bytes into `out` (OMI_AUTH_SHA256_LENGTH bytes).
 * Returns 0 on success, -1 on invalid arguments.
 */
int32_t omi_auth_sha256(const uint8_t* data, size_t length, uint8_t* out);

/**
 * Fills `out` with `length` bytes from the operating system CSPRNG.
 * Returns 0 on success, -1 on invalid arguments or entropy failure.
 */
int32_t omi_auth_random_bytes(uint8_t* out, size_t length);

/**
 * Validates an OAuth callback against the armed redirect URI and expected
 * state. The callback must share the redirect's scheme, host, port and
 * percent-encoded path, carry no userinfo or fragment, contain no duplicate
 * or valueless query keys and no `error`, echo `state`, and carry a
 * non-empty `code`.
 *
 * Returns 1 and writes the percent-decoded, NUL-terminated code into
 * `out_code` when valid; 0 when rejected; -1 on invalid arguments or when
 * `out_code_capacity` is too small.
 */
int32_t omi_auth_callback_code(
    const char* callback,
    const char* redirect_uri,
    const char* expected_state,
    char* out_code,
    size_t out_code_capacity
);

#ifdef __cplusplus
}
#endif

#endif // OMI_AUTH_H
