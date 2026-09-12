#include "omi_backend_recording.h"

#include <cmath>
#include <cstring>

namespace {

bool nonempty_equal(const char* expected, const char* current) {
  return expected != nullptr && current != nullptr && expected[0] != '\0' &&
         std::strcmp(expected, current) == 0;
}

bool string_length_in(const char* value, size_t min, size_t max) {
  if (value == nullptr) {
    return false;
  }
  const size_t length = std::strlen(value);
  return length >= min && length <= max;
}

}  // namespace

int32_t omi_backend_recording_captured_at_valid(double value) {
  return (std::isfinite(value) && value >= 0.0 &&
          value <= OMI_BACKEND_RECORDING_MAX_CAPTURED_AT_MS &&
          std::floor(value) == value)
             ? 1
             : 0;
}

int32_t omi_backend_recording_captured_at_equal(int32_t expected_present,
                                                double expected,
                                                int32_t actual_present,
                                                double actual) {
  const bool left = expected_present != 0;
  const bool right = actual_present != 0;
  if (left != right) {
    return 0;
  }
  if (!left) {
    return 1;
  }
  return expected == actual ? 1 : 0;
}

int32_t omi_backend_recording_retryable_status(int32_t status) {
  return (status == 408 || status == 429 || (status >= 500 && status <= 599))
             ? 1
             : 0;
}

int32_t omi_backend_recording_same_context(const char* expected_login,
                                           const char* current_login,
                                           const char* expected_origin,
                                           const char* current_origin) {
  return (nonempty_equal(expected_login, current_login) &&
          nonempty_equal(expected_origin, current_origin))
             ? 1
             : 0;
}

int32_t omi_backend_recording_remembered_identity(const char* identifier,
                                                  const char* name) {
  return (string_length_in(identifier, 1, 128) &&
          string_length_in(name, 1, 256))
             ? 1
             : 0;
}

int32_t omi_backend_recording_remembered_current(uint64_t ticket,
                                                 uint64_t generation,
                                                 const char* expected_login,
                                                 const char* current_login,
                                                 int32_t ready) {
  return (ticket == generation && ready != 0 &&
          nonempty_equal(expected_login, current_login))
             ? 1
             : 0;
}

int32_t omi_backend_recording_device_valid(const char* device_id,
                                           int32_t name_present,
                                           const char* device_name, double codec) {
  if (!string_length_in(device_id, 1, 256)) {
    return 0;
  }
  if (name_present != 0 && !string_length_in(device_name, 0, 256)) {
    return 0;
  }
  return (std::isfinite(codec) && codec >= 0.0 && codec <= 255.0 &&
          std::floor(codec) == codec)
             ? 1
             : 0;
}

int32_t omi_backend_recording_budget_ok(uint64_t total_bytes,
                                        uint64_t extra_bytes, int32_t creating,
                                        uint32_t file_count) {
  if (total_bytes > OMI_BACKEND_RECORDING_MAX_TOTAL_BYTES ||
      extra_bytes > OMI_BACKEND_RECORDING_MAX_TOTAL_BYTES - total_bytes) {
    return 0;
  }
  if (creating != 0 && file_count >= OMI_BACKEND_RECORDING_MAX_FILES) {
    return 0;
  }
  return 1;
}
