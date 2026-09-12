#include "omi_backend_policy.h"

#include <cstring>
#include <iostream>
#include <string>

static int failures = 0;

static void expect(bool cond, const char* msg) {
  if (!cond) {
    std::cerr << "FAIL: " << msg << "\n";
    ++failures;
  }
}

static void test_route_strip() {
  char out[256];
  expect(omi_backend_route_strip("/v1/tasks?limit=2", out, sizeof(out)) ==
             static_cast<int32_t>(std::strlen("/v1/tasks")),
         "strip query length");
  expect(std::strcmp(out, "/v1/tasks") == 0, "strip query value");
  expect(omi_backend_route_strip("/v1/conversations#frag", out, sizeof(out)) ==
             static_cast<int32_t>(std::strlen("/v1/conversations")),
         "strip fragment length");
  expect(std::strcmp(out, "/v1/conversations") == 0, "strip fragment value");
  expect(omi_backend_route_strip(nullptr, out, sizeof(out)) == -1,
         "strip null path");
}

static void test_capture_paths() {
  expect(omi_backend_is_capture_path("/v1/live/sessions") == 1, "live/sessions");
  expect(omi_backend_is_capture_path("/v1/live/sessions?retry=1") == 1,
         "live/sessions query");
  expect(omi_backend_is_capture_path("/v1/live/sessions-extra") == 0,
         "live/sessions-extra");
  expect(omi_backend_is_capture_path("/v1/chat-messages") == 1, "chat-messages");
  expect(omi_backend_is_capture_path("/v1/chat-messages?limit=50") == 1,
         "chat-messages query");
  expect(omi_backend_is_capture_path("/v1/chat-generations/id/events") == 1,
         "chat-generations prefix");
  expect(omi_backend_is_capture_path("/v1/chat-attachments") == 1,
         "chat-attachments");
  expect(omi_backend_is_capture_path("/v1/chat-attachments/id/complete") == 1,
         "chat-attachments prefix");
  expect(omi_backend_is_capture_path("/v1/device-sessions") == 1,
         "device-sessions");
  expect(omi_backend_is_capture_path("/v1/device-sessions/id/audio") == 1,
         "device-sessions child");
  expect(omi_backend_is_capture_path("/v1/device-sessions-extra") == 0,
         "device-sessions-extra");
  expect(omi_backend_is_capture_path("/v1/settings") == 1, "settings");
  expect(omi_backend_is_capture_path("/v1/conversations") == 1, "conversations");
  expect(omi_backend_is_capture_path("/v1/memories") == 1, "memories");
  expect(omi_backend_is_capture_path("/v1/tasks") == 1, "tasks");
  expect(omi_backend_is_capture_path("/v1/tasks/ops") == 1, "tasks/ops");
  expect(omi_backend_is_capture_path("/v1/tasks/ops?op=complete") == 1,
         "tasks/ops query");
  expect(omi_backend_is_capture_path("/v1/tasks/one") == 0, "tasks/one");
  expect(omi_backend_is_capture_path("/v1/users/me") == 0, "users/me");
  expect(omi_backend_is_capture_path("/v1/conversations#keep") == 1,
         "conversations fragment");
}

static void test_timeouts() {
  expect(omi_backend_request_timeout_seconds(
             "POST", "/v1/device-sessions/id/transcribe") == 150,
         "transcribe timeout");
  expect(omi_backend_request_timeout_seconds(
             "POST", "/v1/device-sessions/id/transcribe?retry=1") == 150,
         "transcribe timeout with query");
  expect(omi_backend_request_timeout_seconds(
             "GET", "/v1/device-sessions/id/transcribe") == 60,
         "get transcribe default");
  expect(omi_backend_request_timeout_seconds(
             "POST", "/v1/device-sessions/id/complete") == 60,
         "complete default");
  expect(omi_backend_request_timeout_seconds(
             "POST", "/v1/device-sessions//transcribe") == 60,
         "empty id default");
  expect(omi_backend_request_timeout_seconds("POST", "/v1/live/sessions") == 60,
         "live sessions default");
  expect(omi_backend_request_timeout_seconds(
             "POST",
             "/v1/device-sessions/11111111-2222-3333-4444-555555555555/"
             "transcribe") == 150,
         "uuid transcribe timeout");
}

static void test_example_platform() {
  expect(omi_backend_example_platform_supported("GET", "/v1/tasks?limit=2") == 1,
         "GET tasks");
  expect(omi_backend_example_platform_supported("GET", "/v1/conversations") == 1,
         "GET conversations");
  expect(omi_backend_example_platform_supported("GET", "/v1/memories") == 1,
         "GET memories");
  expect(omi_backend_example_platform_supported("POST", "/v1/tasks/ops") == 1,
         "POST tasks/ops");
  expect(omi_backend_example_platform_supported("DELETE", "/v1/tasks/ops") == 0,
         "DELETE tasks/ops");
  expect(omi_backend_example_platform_supported("POST", "/v1/tasks") == 0,
         "POST tasks");
}

static void test_hosts() {
  expect(omi_backend_is_loopback_hostname("localhost") == 1, "localhost");
  expect(omi_backend_is_loopback_hostname("127.0.0.1") == 1, "127");
  expect(omi_backend_is_loopback_hostname("[::1]") == 1, "ipv6 loopback");
  expect(omi_backend_is_cloud_hostname("api.omi.me") == 1, "cloud");
  expect(omi_backend_is_cloud_hostname("API.OMI.ME") == 1, "cloud ci");
  expect(omi_backend_is_allowed_v5_hostname("synthetic.workers.dev") == 1,
         "workers");
  expect(omi_backend_is_allowed_v5_hostname("workers.dev") == 0,
         "bare workers.dev");
  expect(omi_backend_is_allowed_v5_hostname("untrusted.invalid") == 0,
         "untrusted");
}

static void test_software_plane() {
  expect(omi_backend_software_plane_is_new(nullptr, 1) == 1, "stamped new");
  expect(omi_backend_software_plane_is_new(nullptr, 0) == 0, "stamped old");
  expect(omi_backend_software_plane_is_new("", 1) == 1, "empty stored new");
  expect(omi_backend_software_plane_is_new("new", 0) == 1, "stored new");
  expect(omi_backend_software_plane_is_new("old", 1) == 0, "stored old");
  expect(omi_backend_software_plane_is_new("unexpected", 1) == 0,
         "unknown stored");
}

int main() {
  test_route_strip();
  test_capture_paths();
  test_timeouts();
  test_example_platform();
  test_hosts();
  test_software_plane();
  if (failures != 0) {
    std::cerr << failures << " failure(s)\n";
    return 1;
  }
  std::cout << "omi_backend_policy tests passed\n";
  return 0;
}
