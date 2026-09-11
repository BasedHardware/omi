#include "omi_backend_http.h"

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

struct FakeInjector {
  int calls = 0;
  std::string method;
  std::string path;
  int32_t timeout_seconds = -1;
  int32_t is_capture_path = -1;
  std::string body;
  int32_t status = 200;
  std::string response = "{\"ok\":true}";
  int32_t result = 0;
};

static int32_t fake_inject(void* user, const omi_backend_http_inject_in* in,
                           int32_t* out_status, char* out_body, size_t out_cap,
                           size_t* out_len) {
  auto* fake = static_cast<FakeInjector*>(user);
  ++fake->calls;
  fake->method = in->method != nullptr ? in->method : "";
  fake->path = in->path != nullptr ? in->path : "";
  fake->timeout_seconds = in->timeout_seconds;
  fake->is_capture_path = in->is_capture_path;
  fake->body = std::string(in->body != nullptr ? in->body : "", in->body_len);
  if (fake->result != 0) {
    return fake->result;
  }
  if (fake->response.size() + 1 > out_cap) {
    return OMI_BACKEND_HTTP_ERR_OVERFLOW;
  }
  std::memcpy(out_body, fake->response.data(), fake->response.size());
  out_body[fake->response.size()] = '\0';
  *out_len = fake->response.size();
  *out_status = fake->status;
  return 0;
}

static void test_request_valid() {
  expect(omi_backend_http_request_valid("GET", "/v1/tasks") == 1, "GET tasks");
  expect(omi_backend_http_request_valid("POST", "/v1/live/sessions") == 1,
         "POST live");
  expect(omi_backend_http_request_valid("PATCH", "/v1/settings") == 1, "PATCH");
  expect(omi_backend_http_request_valid("DELETE", "/v1/tasks") == 1, "DELETE");
  expect(omi_backend_http_request_valid("PUT", "/v1/tasks") == 0, "PUT");
  expect(omi_backend_http_request_valid("GET", "//evil") == 0, "double slash");
  expect(omi_backend_http_request_valid("GET", "/v1/http://x") == 0, "scheme");
  expect(omi_backend_http_request_valid("get", "/v1/tasks") == 0, "case");
  expect(omi_backend_http_request_valid(nullptr, "/v1/tasks") == -1, "null method");
}

static void test_plan() {
  omi_backend_http_plan plan = {};
  expect(omi_backend_http_plan_request(
             "POST", "/v1/device-sessions/id/transcribe", &plan) == 0,
         "plan transcribe");
  expect(plan.valid == 1, "transcribe valid");
  expect(plan.timeout_seconds == 150, "transcribe timeout");
  expect(plan.is_capture_path == 1, "transcribe capture");

  expect(omi_backend_http_plan_request("GET", "/v1/users/me", &plan) == 0,
         "plan users");
  expect(plan.valid == 1, "users valid");
  expect(plan.timeout_seconds == 60, "users timeout");
  expect(plan.is_capture_path == 0, "users not capture");

  expect(omi_backend_http_plan_request("GET", "//nope", &plan) == 0,
         "plan invalid");
  expect(plan.valid == 0, "invalid valid flag");
  expect(plan.timeout_seconds == 0, "invalid timeout zero");
  expect(plan.is_capture_path == 0, "invalid capture zero");
}

static void test_execute_fake_injector() {
  FakeInjector fake;
  char body[64];
  size_t len = 0;
  int32_t status = 0;
  expect(omi_backend_http_execute("POST",
                                  "/v1/device-sessions/abc/transcribe",
                                  "{\"n\":1}", 7, fake_inject, &fake, &status,
                                  body, sizeof(body), &len) == 0,
         "execute transcribe");
  expect(fake.calls == 1, "injector called");
  expect(fake.timeout_seconds == 150, "injector timeout");
  expect(fake.is_capture_path == 1, "injector capture");
  expect(fake.method == "POST", "injector method");
  expect(status == 200, "status");
  expect(std::strcmp(body, "{\"ok\":true}") == 0, "response");

  fake = FakeInjector{};
  expect(omi_backend_http_execute("GET", "/v1/users/me", nullptr, 0, fake_inject,
                                  &fake, &status, body, sizeof(body), &len) ==
             0,
         "execute users");
  expect(fake.timeout_seconds == 60, "users injector timeout");
  expect(fake.is_capture_path == 0, "users injector capture");

  fake = FakeInjector{};
  expect(omi_backend_http_execute("GET", "//evil", nullptr, 0, fake_inject, &fake,
                                  &status, body, sizeof(body), &len) ==
             OMI_BACKEND_HTTP_ERR_INVALID,
         "reject invalid");
  expect(fake.calls == 0, "injector skipped");

  fake = FakeInjector{};
  fake.result = -9;
  expect(omi_backend_http_execute("GET", "/v1/tasks", nullptr, 0, fake_inject,
                                  &fake, &status, body, sizeof(body), &len) ==
             OMI_BACKEND_HTTP_ERR_INJECTOR,
         "injector error");
}

static void test_recording_identity() {
  const char* key =
      "capture-owner-v1:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      "aaaaaaaa";
  expect(std::strlen(key) == std::strlen("capture-owner-v1:") + 64, "key len");
  expect(omi_backend_recording_owner_key_valid(key) == 1, "owner key");
  expect(omi_backend_recording_owner_key_valid("capture-owner-v1:zz") == 0,
         "short key");
  const char* receipt =
      "capture1."
      "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa."
      "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
  expect(omi_backend_recording_receipt_valid(receipt) == 1, "receipt");
  expect(omi_backend_recording_uuid_valid(
             "11111111-2222-4333-8444-555555555555") == 1,
         "uuid");
  expect(omi_backend_recording_uuid_valid(
             "11111111-2222-3333-8444-555555555555") == 0,
         "uuid version");
}

static void test_journal_relpath() {
  const char* partition =
      "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
  const char* id = "11111111-2222-4333-a444-555555555555";
  char out[128];
  expect(omi_backend_recording_journal_relpath(partition, id, out, sizeof(out)) ==
             109,
         "relpath len");
  expect(std::strcmp(out,
                     "0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
                     "abcdef/11111111-2222-4333-a444-555555555555.journal") == 0,
         "relpath value");
  expect(omi_backend_recording_journal_relpath("not-hex", id, out, sizeof(out)) ==
             OMI_BACKEND_HTTP_ERR_INVALID,
         "bad partition");
  expect(omi_backend_recording_journal_relpath(partition, "../x", out,
                                              sizeof(out)) ==
             OMI_BACKEND_HTTP_ERR_INVALID,
         "bad id");
}

static void test_path_owned() {
  const char* session = "11111111-2222-4333-8444-555555555555";
  expect(omi_backend_recording_path_owned("POST", "/v1/device-sessions",
                                         nullptr) == 1,
         "open path");
  expect(omi_backend_recording_path_owned(
             "POST", "/v1/device-sessions/11111111-2222-4333-8444-555555555555/"
                     "audio",
             session) == 1,
         "audio");
  expect(omi_backend_recording_path_owned(
             "POST",
             "/v1/device-sessions/11111111-2222-4333-8444-555555555555/complete",
             session) == 1,
         "complete");
  expect(omi_backend_recording_path_owned(
             "POST",
             "/v1/device-sessions/11111111-2222-4333-8444-555555555555/"
             "transcribe",
             session) == 1,
         "transcribe owned");
  expect(omi_backend_recording_path_owned(
             "GET", "/v1/device-sessions/11111111-2222-4333-8444-555555555555",
             session) == 1,
         "get session");
  expect(omi_backend_recording_path_owned(
             "GET",
             "/v1/device-sessions/11111111-2222-4333-8444-555555555555/"
             "transcript",
             session) == 1,
         "transcript");
  expect(omi_backend_recording_path_owned(
             "POST", "/v1/device-sessions/other/audio", session) == 0,
         "other session");
  expect(omi_backend_recording_path_owned(
             "POST",
             "/v1/device-sessions/11111111-2222-4333-8444-555555555555/../other/"
             "audio",
             session) == 0,
         "traversal");
  expect(omi_backend_recording_path_owned(
             "POST",
             "/v1/device-sessions/11111111-2222-4333-8444-555555555555/audio",
             nullptr) == 0,
         "no session");
}

int main() {
  test_request_valid();
  test_plan();
  test_execute_fake_injector();
  test_recording_identity();
  test_journal_relpath();
  test_path_owned();
  if (failures != 0) {
    std::cerr << failures << " failure(s)\n";
    return 1;
  }
  std::cout << "omi_backend_http tests passed\n";
  return 0;
}
