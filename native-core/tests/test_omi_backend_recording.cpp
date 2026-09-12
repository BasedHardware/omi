#include "omi_backend_recording.h"

#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <string>

static int failures = 0;

static void expect(bool cond, const char* msg) {
  if (!cond) {
    std::cerr << "FAIL: " << msg << "\n";
    ++failures;
  }
}

static void test_captured_at() {
  expect(omi_backend_recording_captured_at_valid(0.0) == 1, "zero");
  expect(omi_backend_recording_captured_at_valid(1720000000123.0) == 1,
         "epoch ms");
  expect(omi_backend_recording_captured_at_valid(
             OMI_BACKEND_RECORDING_MAX_CAPTURED_AT_MS) == 1,
         "max");
  expect(omi_backend_recording_captured_at_valid(-1.0) == 0, "negative");
  expect(omi_backend_recording_captured_at_valid(0.5) == 0, "fraction");
  expect(omi_backend_recording_captured_at_valid(
             OMI_BACKEND_RECORDING_MAX_CAPTURED_AT_MS + 1.0) == 0,
         "over max");
  expect(omi_backend_recording_captured_at_valid(
             std::nan("")) == 0,
         "nan");
  expect(omi_backend_recording_captured_at_valid(
             std::numeric_limits<double>::infinity()) == 0,
         "inf");

  expect(omi_backend_recording_captured_at_equal(0, 0.0, 0, 0.0) == 1,
         "absent matches absent");
  expect(omi_backend_recording_captured_at_equal(1, 5.0, 1, 5.0) == 1,
         "present equal");
  expect(omi_backend_recording_captured_at_equal(1, 5.0, 1, 6.0) == 0,
         "present differ");
  expect(omi_backend_recording_captured_at_equal(0, 0.0, 1, 0.0) == 0,
         "absent vs zero");
  expect(omi_backend_recording_captured_at_equal(1, 0.0, 0, 0.0) == 0,
         "zero vs absent");
}

static void test_retryable_status() {
  for (int status : {408, 429, 500, 503, 599}) {
    expect(omi_backend_recording_retryable_status(status) == 1, "retryable");
  }
  for (int status : {200, 400, 401, 403, 409, 600, 0, -1}) {
    expect(omi_backend_recording_retryable_status(status) == 0, "terminal");
  }
}

static void test_same_context() {
  expect(omi_backend_recording_same_context("login-a", "login-a", "origin-a",
                                            "origin-a") == 1,
         "same");
  expect(omi_backend_recording_same_context("login-a", "login-b", "origin-a",
                                            "origin-a") == 0,
         "login differs");
  expect(omi_backend_recording_same_context("login-a", "login-a", "origin-a",
                                            "origin-b") == 0,
         "origin differs");
  expect(omi_backend_recording_same_context("login-a", nullptr, "origin-a",
                                            "origin-a") == 0,
         "null login");
  expect(omi_backend_recording_same_context("", "login-a", "origin-a",
                                            "origin-a") == 0,
         "empty login");
  expect(omi_backend_recording_same_context("login-a", "login-a", "",
                                            "origin-a") == 0,
         "empty origin");
}

static void test_remembered_identity() {
  expect(omi_backend_recording_remembered_identity("device", "Omi") == 1,
         "identity");
  expect(omi_backend_recording_remembered_identity(nullptr, "Omi") == 0,
         "null id");
  expect(omi_backend_recording_remembered_identity("device", "") == 0,
         "empty name");
  expect(omi_backend_recording_remembered_identity(
             std::string(129, 'x').c_str(), "Omi") == 0,
         "long id");
  expect(omi_backend_recording_remembered_identity(
             "device", std::string(257, 'x').c_str()) == 0,
         "long name");
  expect(omi_backend_recording_remembered_identity(
             std::string(128, 'x').c_str(), std::string(256, 'y').c_str()) == 1,
         "boundaries");

  expect(omi_backend_recording_remembered_current(1, 1, "login", "login", 1) ==
             1,
         "current");
  expect(omi_backend_recording_remembered_current(1, 2, "login", "login", 1) ==
             0,
         "stale ticket");
  expect(omi_backend_recording_remembered_current(1, 1, "login", "other", 1) ==
             0,
         "login changed");
  expect(omi_backend_recording_remembered_current(1, 1, "login", nullptr, 1) ==
             0,
         "null login");
  expect(omi_backend_recording_remembered_current(1, 1, "login", "login", 0) ==
             0,
         "not ready");
}

static void test_device_valid() {
  expect(omi_backend_recording_device_valid("omi-test", 0, nullptr, 21.0) == 1,
         "device no name");
  expect(omi_backend_recording_device_valid("omi-test", 1, "Desk", 21.0) == 1,
         "device with name");
  expect(omi_backend_recording_device_valid("", 0, nullptr, 21.0) == 0,
         "empty id");
  expect(omi_backend_recording_device_valid("omi-test", 0, nullptr, 0.5) == 0,
         "fraction codec");
  expect(omi_backend_recording_device_valid("omi-test", 0, nullptr, 256.0) == 0,
         "over codec");
  expect(omi_backend_recording_device_valid("omi-test", 0, nullptr, -1.0) == 0,
         "negative codec");
  expect(omi_backend_recording_device_valid(std::string(257, 'x').c_str(), 0,
                                            nullptr, 21.0) == 0,
         "long id");
  expect(omi_backend_recording_device_valid("omi-test", 1,
                                            std::string(257, 'x').c_str(),
                                            21.0) == 0,
         "long name");
}

static void test_budget() {
  expect(omi_backend_recording_budget_ok(0, 0, 1, 0) == 1, "empty create");
  expect(omi_backend_recording_budget_ok(OMI_BACKEND_RECORDING_MAX_TOTAL_BYTES,
                                         0, 0, 100) == 1,
         "at byte cap");
  expect(omi_backend_recording_budget_ok(OMI_BACKEND_RECORDING_MAX_TOTAL_BYTES,
                                         1, 0, 0) == 0,
         "over byte cap");
  expect(omi_backend_recording_budget_ok(0, 0, 1,
                                         OMI_BACKEND_RECORDING_MAX_FILES) == 0,
         "at file cap when creating");
  expect(omi_backend_recording_budget_ok(0, 0, 0,
                                         OMI_BACKEND_RECORDING_MAX_FILES) == 1,
         "file cap only blocks create");
}

int main() {
  test_captured_at();
  test_retryable_status();
  test_same_context();
  test_remembered_identity();
  test_device_valid();
  test_budget();
  if (failures != 0) {
    std::cerr << failures << " failure(s)\n";
    return 1;
  }
  std::cout << "omi_backend_recording tests passed\n";
  return 0;
}
