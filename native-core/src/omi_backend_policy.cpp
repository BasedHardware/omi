#include "omi_backend_policy.h"

#include <cctype>
#include <cstring>
#include <string>
#include <string_view>

namespace {

std::string_view strip_route(std::string_view path) {
  const size_t cut = path.find_first_of("?#");
  return cut == std::string_view::npos ? path : path.substr(0, cut);
}

bool equals_ci(std::string_view a, std::string_view b) {
  if (a.size() != b.size()) {
    return false;
  }
  for (size_t i = 0; i < a.size(); ++i) {
    if (std::tolower(static_cast<unsigned char>(a[i])) !=
        std::tolower(static_cast<unsigned char>(b[i]))) {
      return false;
    }
  }
  return true;
}

std::string_view normalize_host(std::string_view host) {
  if (host.size() >= 2 && host.front() == '[' && host.back() == ']') {
    return host.substr(1, host.size() - 2);
  }
  return host;
}

bool starts_with(std::string_view value, std::string_view prefix) {
  return value.size() >= prefix.size() && value.substr(0, prefix.size()) == prefix;
}

bool is_capture_route(std::string_view route) {
  return route == "/v1/settings" || route == "/v1/live/sessions" ||
         route == "/v1/chat-messages" || starts_with(route, "/v1/chat-generations/") ||
         route == "/v1/chat-attachments" ||
         starts_with(route, "/v1/chat-attachments/") ||
         route == "/v1/device-sessions" ||
         starts_with(route, "/v1/device-sessions/") ||
         route == "/v1/conversations" || route == "/v1/memories" ||
         route == "/v1/tasks" || route == "/v1/tasks/ops";
}

// Match Apple OmiRequestTimeout: URL path split on '/', leading empty segment.
bool is_transcribe_timeout_path(std::string_view path) {
  const std::string_view route = strip_route(path);
  // Expect: "" / "v1" / "device-sessions" / "<id>" / "transcribe"
  if (!starts_with(route, "/v1/device-sessions/")) {
    return false;
  }
  std::string_view rest = route.substr(std::strlen("/v1/device-sessions/"));
  if (rest.empty() || rest.front() == '/') {
    return false;
  }
  const size_t slash = rest.find('/');
  if (slash == std::string_view::npos || slash == 0) {
    return false;
  }
  const std::string_view id = rest.substr(0, slash);
  const std::string_view tail = rest.substr(slash + 1);
  return !id.empty() && id.find('/') == std::string_view::npos &&
         tail == "transcribe";
}

}  // namespace

int32_t omi_backend_route_strip(const char* path, char* out, size_t out_cap) {
  if (path == nullptr || out == nullptr || out_cap == 0) {
    return -1;
  }
  const std::string_view route = strip_route(path);
  if (route.size() + 1 > out_cap) {
    return -1;
  }
  std::memcpy(out, route.data(), route.size());
  out[route.size()] = '\0';
  return static_cast<int32_t>(route.size());
}

int32_t omi_backend_is_capture_path(const char* path) {
  if (path == nullptr) {
    return -1;
  }
  return is_capture_route(strip_route(path)) ? 1 : 0;
}

int32_t omi_backend_request_timeout_seconds(const char* method,
                                           const char* path) {
  if (method == nullptr || path == nullptr) {
    return 60;
  }
  if (std::strcmp(method, "POST") == 0 && is_transcribe_timeout_path(path)) {
    return 150;
  }
  return 60;
}

int32_t omi_backend_example_platform_supported(const char* method,
                                              const char* path) {
  if (method == nullptr || path == nullptr) {
    return -1;
  }
  const std::string_view route = strip_route(path);
  if (std::strcmp(method, "GET") == 0) {
    return (route == "/v1/conversations" || route == "/v1/memories" ||
            route == "/v1/tasks")
               ? 1
               : 0;
  }
  if (std::strcmp(method, "POST") == 0 && route == "/v1/tasks/ops") {
    return 1;
  }
  return 0;
}

int32_t omi_backend_is_loopback_hostname(const char* hostname) {
  if (hostname == nullptr) {
    return -1;
  }
  const std::string_view host = normalize_host(hostname);
  return (equals_ci(host, "localhost") || equals_ci(host, "127.0.0.1") ||
          equals_ci(host, "::1"))
             ? 1
             : 0;
}

int32_t omi_backend_is_cloud_hostname(const char* hostname) {
  if (hostname == nullptr) {
    return -1;
  }
  return equals_ci(normalize_host(hostname), "api.omi.me") ? 1 : 0;
}

int32_t omi_backend_is_allowed_v5_hostname(const char* hostname) {
  if (hostname == nullptr) {
    return -1;
  }
  if (omi_backend_is_loopback_hostname(hostname) == 1 ||
      omi_backend_is_cloud_hostname(hostname) == 1) {
    return 1;
  }
  std::string lower;
  lower.reserve(std::strlen(hostname));
  for (const char* p = hostname; *p; ++p) {
    lower.push_back(static_cast<char>(
        std::tolower(static_cast<unsigned char>(*p))));
  }
  std::string_view host = normalize_host(lower);
  constexpr std::string_view suffix = ".workers.dev";
  return (host.size() > suffix.size() &&
          host.substr(host.size() - suffix.size()) == suffix)
             ? 1
             : 0;
}
