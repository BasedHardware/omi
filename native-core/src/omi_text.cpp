#include "omi_text.h"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstring>
#include <string>

namespace {

enum class Sequence { kValid, kInvalid, kTruncated };

struct Scan {
  Sequence kind;
  size_t length;
};

// Unicode Table 3-7: classifies the sequence starting at `index`. For an
// invalid sequence `length` is its maximal subpart (at least one byte).
Scan scan_sequence(const uint8_t* data, size_t length, size_t index) {
  const uint8_t lead = data[index];
  if (lead < 0x80) return {Sequence::kValid, 1};
  size_t needed = 0;
  uint8_t low = 0x80;
  uint8_t high = 0xBF;
  if (lead >= 0xC2 && lead <= 0xDF) {
    needed = 1;
  } else if (lead == 0xE0) {
    needed = 2;
    low = 0xA0;
  } else if ((lead >= 0xE1 && lead <= 0xEC) || lead == 0xEE || lead == 0xEF) {
    needed = 2;
  } else if (lead == 0xED) {
    needed = 2;
    high = 0x9F;
  } else if (lead == 0xF0) {
    needed = 3;
    low = 0x90;
  } else if (lead >= 0xF1 && lead <= 0xF3) {
    needed = 3;
  } else if (lead == 0xF4) {
    needed = 3;
    high = 0x8F;
  } else {
    return {Sequence::kInvalid, 1};
  }
  for (size_t offset = 1; offset <= needed; ++offset) {
    if (index + offset >= length) return {Sequence::kTruncated, offset};
    const uint8_t next = data[index + offset];
    const uint8_t min = offset == 1 ? low : 0x80;
    const uint8_t max = offset == 1 ? high : 0xBF;
    if (next < min || next > max) return {Sequence::kInvalid, offset};
  }
  return {Sequence::kValid, needed + 1};
}

bool json_digit(char c) { return c >= '0' && c <= '9'; }

}  // namespace

int32_t omi_utf8_complete_prefix(const uint8_t* data, size_t length,
                                 size_t* out_complete) {
  if ((data == nullptr && length != 0) || out_complete == nullptr) return -1;
  size_t index = 0;
  while (index < length) {
    const Scan scan = scan_sequence(data, length, index);
    if (scan.kind == Sequence::kInvalid) return -1;
    if (scan.kind == Sequence::kTruncated) break;
    index += scan.length;
  }
  *out_complete = index;
  return 0;
}

int32_t omi_utf8_lossy(const uint8_t* data, size_t length, uint8_t* out,
                       size_t out_capacity, size_t* out_length) {
  if ((data == nullptr && length != 0) || out_length == nullptr ||
      (out == nullptr && length != 0) || out_capacity / 3 < length) {
    return -1;
  }
  size_t written = 0;
  size_t index = 0;
  while (index < length) {
    const Scan scan = scan_sequence(data, length, index);
    if (scan.kind == Sequence::kValid) {
      std::memcpy(out + written, data + index, scan.length);
      written += scan.length;
    } else {
      out[written++] = 0xEF;
      out[written++] = 0xBF;
      out[written++] = 0xBD;
    }
    index += scan.length;
  }
  *out_length = written;
  return 0;
}

int32_t omi_json_format_number(double value, char* out, size_t out_capacity) {
  if (out == nullptr || !std::isfinite(value)) return -1;
  std::string text;
  if (value == 0) {
    text = "0";
  } else {
    char buffer[64];
    const auto result =
        std::to_chars(buffer, buffer + sizeof(buffer), std::fabs(value),
                      std::chars_format::scientific);
    if (result.ec != std::errc()) return -1;
    const std::string scientific(buffer, result.ptr);
    const size_t exponent_at = scientific.find('e');
    std::string digits = scientific.substr(0, exponent_at);
    digits.erase(std::remove(digits.begin(), digits.end(), '.'), digits.end());
    const int exponent = std::stoi(scientific.substr(exponent_at + 1));
    const int k = static_cast<int>(digits.size());
    const int n = exponent + 1;
    if (value < 0) text = "-";
    if (k <= n && n <= 21) {
      text += digits + std::string(static_cast<size_t>(n - k), '0');
    } else if (0 < n && n <= 21) {
      text += digits.substr(0, static_cast<size_t>(n)) + "." +
              digits.substr(static_cast<size_t>(n));
    } else if (-6 < n && n <= 0) {
      text += "0." + std::string(static_cast<size_t>(-n), '0') + digits;
    } else {
      text += digits.substr(0, 1);
      if (k > 1) text += "." + digits.substr(1);
      text += n - 1 < 0 ? "e-" : "e+";
      text += std::to_string(std::abs(n - 1));
    }
  }
  if (text.size() + 1 > out_capacity) return -1;
  std::memcpy(out, text.c_str(), text.size() + 1);
  return static_cast<int32_t>(text.size());
}

int32_t omi_json_number_valid(const char* text, size_t length) {
  if (text == nullptr) return 0;
  size_t index = 0;
  if (index < length && text[index] == '-') ++index;
  if (index >= length) return 0;
  if (text[index] == '0') {
    ++index;
  } else if (text[index] >= '1' && text[index] <= '9') {
    while (index < length && json_digit(text[index])) ++index;
  } else {
    return 0;
  }
  if (index < length && text[index] == '.') {
    ++index;
    if (index >= length || !json_digit(text[index])) return 0;
    while (index < length && json_digit(text[index])) ++index;
  }
  if (index < length && (text[index] == 'e' || text[index] == 'E')) {
    ++index;
    if (index < length && (text[index] == '+' || text[index] == '-')) ++index;
    if (index >= length || !json_digit(text[index])) return 0;
    while (index < length && json_digit(text[index])) ++index;
  }
  return index == length ? 1 : 0;
}
