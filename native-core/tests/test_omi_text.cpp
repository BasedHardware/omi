#include "omi_text.h"

#include <cmath>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

static int failures = 0;

static void expect(bool cond, const std::string& msg) {
  if (!cond) {
    std::cerr << "FAIL: " << msg << "\n";
    ++failures;
  }
}

static std::string format(double value) {
  char out[32];
  const int32_t written = omi_json_format_number(value, out, sizeof(out));
  return written < 0 ? std::string("<err>") : std::string(out, written);
}

static long complete(const std::vector<uint8_t>& bytes) {
  size_t prefix = 99;
  if (omi_utf8_complete_prefix(bytes.data(), bytes.size(), &prefix) != 0) {
    return -1;
  }
  return static_cast<long>(prefix);
}

static std::vector<uint8_t> lossy(const std::vector<uint8_t>& bytes) {
  std::vector<uint8_t> out(bytes.size() * 3);
  size_t written = 0;
  if (omi_utf8_lossy(bytes.data(), bytes.size(), out.data(), out.size(),
                     &written) != 0) {
    return {0};
  }
  out.resize(written);
  return out;
}

static void test_utf8() {
  expect(complete({}) == 0, "empty");
  expect(complete({'a', 'b'}) == 2, "ascii");
  expect(complete({0xC3, 0xA9}) == 2, "two byte");
  expect(complete({'a', 0xE2, 0x82}) == 1, "truncated three byte held");
  expect(complete({0xF0, 0x9F, 0x98}) == 0, "truncated four byte held");
  expect(complete({0xF4, 0x8F, 0xBF, 0xBF}) == 4, "max scalar");
  expect(complete({0xFF}) == -1, "invalid lead");
  expect(complete({0xC0, 0x80}) == -1, "overlong");
  expect(complete({0xE0, 0x80, 0x80}) == -1, "overlong three byte");
  expect(complete({0xED, 0xA0, 0x80}) == -1, "surrogate");
  expect(complete({0xF4, 0x90, 0x80, 0x80}) == -1, "above max");
  expect(complete({0xE2, 'a'}) == -1, "bad continuation");
  size_t prefix = 0;
  expect(omi_utf8_complete_prefix(nullptr, 1, &prefix) == -1, "null data");

  const std::vector<uint8_t> fffd = {0xEF, 0xBF, 0xBD};
  expect(lossy({'a'}) == std::vector<uint8_t>({'a'}), "lossy ascii");
  expect(lossy({0xFF, 'a'}) == std::vector<uint8_t>({0xEF, 0xBF, 0xBD, 'a'}),
         "lossy invalid lead");
  expect(lossy({0xE2, 0x82, 'a'}) ==
             std::vector<uint8_t>({0xEF, 0xBF, 0xBD, 'a'}),
         "lossy maximal subpart is one replacement");
  expect(lossy({0xF0, 0x80}) ==
             std::vector<uint8_t>({0xEF, 0xBF, 0xBD, 0xEF, 0xBF, 0xBD}),
         "lossy F0 80 is two replacements");
  expect(lossy({0xE2, 0x82}) == fffd, "lossy truncated tail");
  expect(lossy({0xC3, 0xA9}) == std::vector<uint8_t>({0xC3, 0xA9}),
         "lossy valid kept");
  uint8_t small[2];
  size_t written = 0;
  const uint8_t one[] = {'a'};
  expect(omi_utf8_lossy(one, 1, small, sizeof(small), &written) == -1,
         "lossy capacity");
}

static void test_format() {
  expect(format(0) == "0", "zero");
  expect(format(-0.0) == "0", "negative zero");
  expect(format(1) == "1", "one");
  expect(format(-1.5) == "-1.5", "negative fraction");
  expect(format(0.1) == "0.1", "0.1");
  expect(format(0.1 + 0.2) == "0.30000000000000004", "0.1+0.2");
  expect(format(1e-7) == "1e-7", "1e-7");
  expect(format(1.5e-7) == "1.5e-7", "1.5e-7");
  expect(format(0.000001) == "0.000001", "1e-6");
  expect(format(1e21) == "1e+21", "1e21");
  expect(format(1e20) == "100000000000000000000", "1e20");
  expect(format(123456789012345680000.0) == "123456789012345680000", "big");
  expect(format(1.7976931348623157e308) == "1.7976931348623157e+308", "max");
  expect(format(5e-324) == "5e-324", "min subnormal");
  expect(format(9007199254740993.0) == "9007199254740992", "beyond safe");
  expect(format(std::nan("")) == "<err>", "nan");
  expect(format(std::numeric_limits<double>::infinity()) == "<err>", "inf");
  char tiny[2];
  expect(omi_json_format_number(10, tiny, sizeof(tiny)) == -1, "capacity");
}

static void test_number_valid() {
  for (const char* good : {"0", "-0", "1", "-12", "1.5", "0.5", "1e5", "1E+5",
                           "1e-5", "-1.25e10"}) {
    expect(omi_json_number_valid(good, std::string(good).size()) == 1, good);
  }
  for (const char* bad : {"", "-", "01", "+1", "1.", ".5", "1e", "1e+", "--1",
                          "1-2", "1.2.3", "0x10", "1ee5", "Infinity"}) {
    expect(omi_json_number_valid(bad, std::string(bad).size()) == 0, bad);
  }
  expect(omi_json_number_valid(nullptr, 0) == 0, "null");
}

int main() {
  test_utf8();
  test_format();
  test_number_valid();
  if (failures != 0) {
    std::cerr << failures << " failure(s)\n";
    return 1;
  }
  std::cout << "omi_text: all tests passed\n";
  return 0;
}
