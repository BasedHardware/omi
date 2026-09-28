#ifndef OMI_BACKEND_HTTP_H
#define OMI_BACKEND_HTTP_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define OMI_BACKEND_HTTP_OK 0
#define OMI_BACKEND_HTTP_ERR_INVALID -1
#define OMI_BACKEND_HTTP_ERR_OVERFLOW -2
#define OMI_BACKEND_HTTP_ERR_INJECTOR -3

/**
 * Shared HTTP facade (C ABI). Plans timeout/capture/validity, then calls a
 * platform injector. TLS, keychain, and the real session stay in the shim.
 */

typedef struct omi_backend_http_plan {
  int32_t valid;
  int32_t timeout_seconds;
  int32_t is_capture_path;
} omi_backend_http_plan;

int32_t omi_backend_http_request_valid(const char* method, const char* path);

int32_t omi_backend_http_plan_request(const char* method, const char* path,
                                      omi_backend_http_plan* out);

typedef struct omi_backend_http_inject_in {
  const char* method;
  const char* path;
  int32_t timeout_seconds;
  int32_t is_capture_path;
  const char* body;
  size_t body_len;
} omi_backend_http_inject_in;

typedef int32_t (*omi_backend_http_injector)(void* user,
                                             const omi_backend_http_inject_in* in,
                                             int32_t* out_status, char* out_body,
                                             size_t out_cap, size_t* out_len);

int32_t omi_backend_http_execute(const char* method, const char* path,
                                 const char* body, size_t body_len,
                                 omi_backend_http_injector injector, void* user,
                                 int32_t* out_status, char* out_body,
                                 size_t out_cap, size_t* out_len);

int32_t omi_backend_recording_owner_key_valid(const char* owner_key);
int32_t omi_backend_recording_receipt_valid(const char* receipt);
int32_t omi_backend_recording_uuid_valid(const char* value);

int32_t omi_backend_recording_journal_relpath(const char* partition_hex,
                                              const char* capture_id, char* out,
                                              size_t out_cap);

int32_t omi_backend_recording_path_owned(const char* method, const char* path,
                                         const char* session_id);

#ifdef __cplusplus
}
#endif

#endif /* OMI_BACKEND_HTTP_H */
