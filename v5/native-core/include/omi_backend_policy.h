#ifndef OMI_BACKEND_POLICY_H
#define OMI_BACKEND_POLICY_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Shared backend policy (C ABI). Source of truth for capture-path allowlist,
 * route stripping, request timeouts, and example-platform method+path rules.
 * Platform shims call these; credential-bearing HTTP stays in the shims.
 */

/** Strip path at the first '?' or '#'. Writes UTF-8 without NUL into out.
 *  Returns written length, or -1 on invalid args / overflow. */
int32_t omi_backend_route_strip(const char* path, char* out, size_t out_cap);

/** 1 if path is a capture/v5 backend route, 0 otherwise, -1 on null path. */
int32_t omi_backend_is_capture_path(const char* path);

/**
 * Request timeout in seconds.
 * POST /v1/device-sessions/<id>/transcribe → 150; otherwise → 60.
 * Matches Apple OmiRequestTimeout (path segments; id must be non-empty).
 */
int32_t omi_backend_request_timeout_seconds(const char* method, const char* path);

/** 1 if example-platform allows method+path, 0 otherwise, -1 on null args. */
int32_t omi_backend_example_platform_supported(const char* method,
                                              const char* path);

/** Hostname helpers (ASCII, case-insensitive). Bracketed IPv6 stripped. */
int32_t omi_backend_is_loopback_hostname(const char* hostname);
int32_t omi_backend_is_cloud_hostname(const char* hostname);
int32_t omi_backend_is_allowed_v5_hostname(const char* hostname);

/**
 * 1 when the new software plane is selected. A non-empty stored preference
 * wins ("new" only); otherwise the stamped v5 origin decides.
 */
int32_t omi_backend_software_plane_is_new(const char* stored,
                                          int32_t stamped_valid);

#ifdef __cplusplus
}
#endif

#endif /* OMI_BACKEND_POLICY_H */
