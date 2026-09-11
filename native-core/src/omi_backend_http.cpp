#include "omi_backend_http.h"

#include "omi_backend_policy.h"

#include <cstring>
#include <string_view>

namespace {

bool eq(const char* value, const char* expected) {
  return value != nullptr && std::strcmp(value, expected) == 0;
}

bool is_lower_hex(std::string_view value) {
  for (char c : value) {
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) {
      return false;
    }
  }
  return !value.empty();
}

bool is_uuid_v4(std::string_view value) {
  if (value.size() != 36) {
    return false;
  }
  if (value[8] != '-' || value[13] != '-' || value[18] != '-' ||
      value[23] != '-') {
    return false;
  }
  if (value[14] != '4') {
    return false;
  }
  const char variant = value[19];
  if (variant != '8' && variant != '9' && variant != 'a' && variant != 'b') {
    return false;
  }
  auto hex_span = [&](size_t begin, size_t end) {
    return is_lower_hex(value.substr(begin, end - begin));
  };
  return hex_span(0, 8) && hex_span(9, 13) && hex_span(14, 18) &&
         hex_span(19, 23) && hex_span(24, 36);
}

bool method_allowed(const char* method) {
  return eq(method, "GET") || eq(method, "POST") || eq(method, "PATCH") ||
         eq(method, "DELETE");
}

bool path_allowed(const char* path) {
  if (path == nullptr || path[0] != '/' || path[1] == '/') {
    return false;
  }
  return std::strstr(path, "://") == nullptr;
}

int32_t write_string(std::string_view value, char* out, size_t out_cap) {
  if (out == nullptr || value.size() + 1 > out_cap) {
    return OMI_BACKEND_HTTP_ERR_OVERFLOW;
  }
  std::memcpy(out, value.data(), value.size());
  out[value.size()] = '\0';
  return static_cast<int32_t>(value.size());
}

}  // namespace

int32_t omi_backend_http_request_valid(const char* method, const char* path) {
  if (method == nullptr || path == nullptr) {
    return -1;
  }
  return method_allowed(method) && path_allowed(path) ? 1 : 0;
}

int32_t omi_backend_http_plan_request(const char* method, const char* path,
                                      omi_backend_http_plan* out) {
  if (out == nullptr) {
    return OMI_BACKEND_HTTP_ERR_INVALID;
  }
  std::memset(out, 0, sizeof(*out));
  const int32_t valid = omi_backend_http_request_valid(method, path);
  if (valid < 0) {
    return OMI_BACKEND_HTTP_ERR_INVALID;
  }
  out->valid = valid;
  if (valid != 1) {
    return OMI_BACKEND_HTTP_OK;
  }
  out->timeout_seconds = omi_backend_request_timeout_seconds(method, path);
  out->is_capture_path = omi_backend_is_capture_path(path) == 1 ? 1 : 0;
  return OMI_BACKEND_HTTP_OK;
}

int32_t omi_backend_http_execute(const char* method, const char* path,
                                 const char* body, size_t body_len,
                                 omi_backend_http_injector injector, void* user,
                                 int32_t* out_status, char* out_body,
                                 size_t out_cap, size_t* out_len) {
  if (injector == nullptr || out_status == nullptr || out_len == nullptr) {
    return OMI_BACKEND_HTTP_ERR_INVALID;
  }
  if (body_len > 0 && body == nullptr) {
    return OMI_BACKEND_HTTP_ERR_INVALID;
  }
  if (out_cap > 0 && out_body == nullptr) {
    return OMI_BACKEND_HTTP_ERR_INVALID;
  }
  omi_backend_http_plan plan = {};
  if (omi_backend_http_plan_request(method, path, &plan) != OMI_BACKEND_HTTP_OK ||
      plan.valid != 1) {
    return OMI_BACKEND_HTTP_ERR_INVALID;
  }
  omi_backend_http_inject_in in = {};
  in.method = method;
  in.path = path;
  in.timeout_seconds = plan.timeout_seconds;
  in.is_capture_path = plan.is_capture_path;
  in.body = body;
  in.body_len = body_len;
  *out_status = 0;
  *out_len = 0;
  const int32_t injected =
      injector(user, &in, out_status, out_body, out_cap, out_len);
  if (injected != 0) {
    return injected == OMI_BACKEND_HTTP_ERR_OVERFLOW
               ? OMI_BACKEND_HTTP_ERR_OVERFLOW
               : OMI_BACKEND_HTTP_ERR_INJECTOR;
  }
  if (*out_len > out_cap) {
    return OMI_BACKEND_HTTP_ERR_OVERFLOW;
  }
  return OMI_BACKEND_HTTP_OK;
}

int32_t omi_backend_recording_owner_key_valid(const char* owner_key) {
  if (owner_key == nullptr) {
    return -1;
  }
  constexpr std::string_view prefix = "capture-owner-v1:";
  const std::string_view value = owner_key;
  if (value.size() != prefix.size() + 64 ||
      value.substr(0, prefix.size()) != prefix) {
    return 0;
  }
  return is_lower_hex(value.substr(prefix.size())) ? 1 : 0;
}

int32_t omi_backend_recording_receipt_valid(const char* receipt) {
  if (receipt == nullptr) {
    return -1;
  }
  constexpr std::string_view prefix = "capture1.";
  const std::string_view value = receipt;
  if (value.size() != prefix.size() + 64 + 1 + 64 ||
      value.substr(0, prefix.size()) != prefix || value[prefix.size() + 64] != '.') {
    return 0;
  }
  return (is_lower_hex(value.substr(prefix.size(), 64)) &&
          is_lower_hex(value.substr(prefix.size() + 65, 64)))
             ? 1
             : 0;
}

int32_t omi_backend_recording_uuid_valid(const char* value) {
  if (value == nullptr) {
    return -1;
  }
  return is_uuid_v4(value) ? 1 : 0;
}

int32_t omi_backend_recording_journal_relpath(const char* partition_hex,
                                              const char* capture_id, char* out,
                                              size_t out_cap) {
  if (partition_hex == nullptr || capture_id == nullptr) {
    return OMI_BACKEND_HTTP_ERR_INVALID;
  }
  const std::string_view partition = partition_hex;
  if (partition.size() != 64 || !is_lower_hex(partition) ||
      !is_uuid_v4(capture_id)) {
    return OMI_BACKEND_HTTP_ERR_INVALID;
  }
  char buffer[64 + 1 + 36 + 8];
  std::memcpy(buffer, partition.data(), partition.size());
  buffer[64] = '/';
  std::memcpy(buffer + 65, capture_id, 36);
  std::memcpy(buffer + 101, ".journal", 8);
  return write_string(std::string_view(buffer, 109), out, out_cap);
}

int32_t omi_backend_recording_path_owned(const char* method, const char* path,
                                         const char* session_id) {
  if (method == nullptr || path == nullptr) {
    return -1;
  }
  if (eq(method, "POST") && eq(path, "/v1/device-sessions")) {
    return 1;
  }
  if (session_id == nullptr || session_id[0] == '\0' ||
      !is_uuid_v4(session_id)) {
    return 0;
  }
  char base[22 + 36 + 1];
  constexpr std::string_view prefix = "/v1/device-sessions/";
  std::memcpy(base, prefix.data(), prefix.size());
  std::memcpy(base + prefix.size(), session_id, 36);
  base[prefix.size() + 36] = '\0';
  const std::string_view owned = base;
  const std::string_view route = path;
  auto is_suffix = [&](std::string_view suffix) {
    if (route.size() != owned.size() + suffix.size()) {
      return false;
    }
    return route.substr(0, owned.size()) == owned &&
           route.substr(owned.size()) == suffix;
  };
  if (eq(method, "POST") &&
      (is_suffix("/audio") || is_suffix("/complete") ||
       is_suffix("/transcribe"))) {
    return 1;
  }
  if (eq(method, "GET") && (route == owned || is_suffix("/transcript"))) {
    return 1;
  }
  return 0;
}
