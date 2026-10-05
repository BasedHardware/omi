#include "omi_auth.h"

#include <algorithm>
#include <array>
#include <cstring>
#include <map>
#include <optional>
#include <string>
#include <string_view>

#if defined(_WIN32)
#include <windows.h>
#include <bcrypt.h>
#if defined(_MSC_VER)
#pragma comment(lib, "bcrypt")
#endif
#elif defined(__APPLE__) || defined(__ANDROID__) || defined(__FreeBSD__) || \
    defined(__OpenBSD__)
#include <stdlib.h>
#elif defined(__linux__)
#include <cerrno>
#include <sys/random.h>
#else
#error "omi_auth: no CSPRNG for this platform"
#endif

namespace {

constexpr std::array<uint32_t, 64> kSha256K = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

constexpr uint32_t rotr(uint32_t value, int bits) {
  return (value >> bits) | (value << (32 - bits));
}

void sha256_block(std::array<uint32_t, 8>& state, const uint8_t* block) {
  std::array<uint32_t, 64> w{};
  for (size_t i = 0; i < 16; ++i) {
    w[i] = (uint32_t{block[i * 4]} << 24) | (uint32_t{block[i * 4 + 1]} << 16) |
           (uint32_t{block[i * 4 + 2]} << 8) | uint32_t{block[i * 4 + 3]};
  }
  for (size_t i = 16; i < 64; ++i) {
    const uint32_t s0 =
        rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
    const uint32_t s1 =
        rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  uint32_t a = state[0], b = state[1], c = state[2], d = state[3];
  uint32_t e = state[4], f = state[5], g = state[6], h = state[7];
  for (size_t i = 0; i < 64; ++i) {
    const uint32_t s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
    const uint32_t ch = (e & f) ^ (~e & g);
    const uint32_t t1 = h + s1 + ch + kSha256K[i] + w[i];
    const uint32_t s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
    const uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
    const uint32_t t2 = s0 + maj;
    h = g;
    g = f;
    f = e;
    e = d + t1;
    d = c;
    c = b;
    b = a;
    a = t1 + t2;
  }
  state[0] += a;
  state[1] += b;
  state[2] += c;
  state[3] += d;
  state[4] += e;
  state[5] += f;
  state[6] += g;
  state[7] += h;
}

struct ParsedURL {
  std::string scheme;
  bool has_authority = false;
  bool has_userinfo = false;
  std::string host;
  std::optional<uint32_t> port;
  std::string path;
  std::optional<std::string> query;
  bool has_fragment = false;
};

bool is_hex(char c) {
  return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') ||
         (c >= 'A' && c <= 'F');
}

int hex_value(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return c - 'A' + 10;
}

bool is_alpha(char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); }

bool is_digit(char c) { return c >= '0' && c <= '9'; }

// RFC 3986 characters plus '%' escapes; anything else makes the URL invalid.
bool valid_url_characters(std::string_view value) {
  for (size_t i = 0; i < value.size(); ++i) {
    const char c = value[i];
    if (c == '%') {
      if (i + 2 >= value.size() || !is_hex(value[i + 1]) ||
          !is_hex(value[i + 2])) {
        return false;
      }
      i += 2;
      continue;
    }
    if (is_alpha(c) || is_digit(c) ||
        std::strchr("-._~:/?#[]@!$&'()*+,;=", c) != nullptr) {
      continue;
    }
    return false;
  }
  return true;
}

std::string lowercase(std::string_view value) {
  std::string out(value);
  for (char& c : out) {
    if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
  }
  return out;
}

std::optional<ParsedURL> parse_url(std::string_view value) {
  if (value.empty() || !valid_url_characters(value)) return std::nullopt;
  ParsedURL url;
  std::string_view rest = value;

  const size_t fragment = rest.find('#');
  if (fragment != std::string_view::npos) {
    url.has_fragment = true;
    rest = rest.substr(0, fragment);
  }
  const size_t query = rest.find('?');
  if (query != std::string_view::npos) {
    url.query = std::string(rest.substr(query + 1));
    rest = rest.substr(0, query);
  }

  const size_t colon = rest.find(':');
  const size_t slash = rest.find('/');
  if (colon != std::string_view::npos &&
      (slash == std::string_view::npos || colon < slash)) {
    const std::string_view scheme = rest.substr(0, colon);
    if (scheme.empty() || !is_alpha(scheme[0])) return std::nullopt;
    for (char c : scheme) {
      if (!is_alpha(c) && !is_digit(c) && c != '+' && c != '-' && c != '.') {
        return std::nullopt;
      }
    }
    url.scheme = std::string(scheme);
    rest = rest.substr(colon + 1);
  }

  if (rest.substr(0, 2) == "//") {
    url.has_authority = true;
    rest = rest.substr(2);
    const size_t end = rest.find('/');
    std::string_view authority = rest.substr(0, end);
    rest = end == std::string_view::npos ? std::string_view{} : rest.substr(end);

    const size_t at = authority.rfind('@');
    if (at != std::string_view::npos) {
      url.has_userinfo = true;
      authority = authority.substr(at + 1);
    }
    std::string_view port_text;
    if (!authority.empty() && authority[0] == '[') {
      const size_t close = authority.find(']');
      if (close == std::string_view::npos) return std::nullopt;
      url.host = std::string(authority.substr(0, close + 1));
      const std::string_view after = authority.substr(close + 1);
      if (!after.empty()) {
        if (after[0] != ':') return std::nullopt;
        port_text = after.substr(1);
      }
    } else {
      const size_t port_colon = authority.find(':');
      url.host = std::string(authority.substr(0, port_colon));
      if (port_colon != std::string_view::npos) {
        port_text = authority.substr(port_colon + 1);
      }
    }
    if (url.host.find('[') != std::string::npos ||
        (url.host.find(']') != std::string::npos && url.host[0] != '[')) {
      return std::nullopt;
    }
    if (!port_text.empty()) {
      uint32_t port = 0;
      for (char c : port_text) {
        if (!is_digit(c)) return std::nullopt;
        port = port * 10 + static_cast<uint32_t>(c - '0');
        if (port > 65535) return std::nullopt;
      }
      url.port = port;
    }
  }
  url.path = std::string(rest);
  return url;
}

bool valid_utf8(const std::string& value) {
  size_t i = 0;
  while (i < value.size()) {
    const auto c = static_cast<unsigned char>(value[i]);
    size_t extra = 0;
    uint32_t code = 0;
    if (c < 0x80) {
      ++i;
      continue;
    } else if ((c & 0xE0) == 0xC0) {
      extra = 1;
      code = c & 0x1F;
    } else if ((c & 0xF0) == 0xE0) {
      extra = 2;
      code = c & 0x0F;
    } else if ((c & 0xF8) == 0xF0) {
      extra = 3;
      code = c & 0x07;
    } else {
      return false;
    }
    if (i + extra >= value.size()) {
      return false;
    }
    for (size_t k = 1; k <= extra; ++k) {
      const auto next = static_cast<unsigned char>(value[i + k]);
      if ((next & 0xC0) != 0x80) return false;
      code = (code << 6) | (next & 0x3F);
    }
    if ((extra == 1 && code < 0x80) || (extra == 2 && code < 0x800) ||
        (extra == 3 && code < 0x10000) || code > 0x10FFFF ||
        (code >= 0xD800 && code <= 0xDFFF)) {
      return false;
    }
    i += extra + 1;
  }
  return true;
}

std::optional<std::string> percent_decode(std::string_view value) {
  std::string out;
  out.reserve(value.size());
  for (size_t i = 0; i < value.size(); ++i) {
    if (value[i] == '%') {
      const char decoded =
          static_cast<char>(hex_value(value[i + 1]) * 16 + hex_value(value[i + 2]));
      if (decoded == '\0') return std::nullopt;
      out.push_back(decoded);
      i += 2;
    } else {
      out.push_back(value[i]);
    }
  }
  if (!valid_utf8(out)) return std::nullopt;
  return out;
}

}  // namespace

int32_t omi_auth_sha256(const uint8_t* data, size_t length, uint8_t* out) {
  if ((data == nullptr && length != 0) || out == nullptr) return -1;
  std::array<uint32_t, 8> state = {0x6a09e667, 0xbb67ae85, 0x3c6ef372,
                                   0xa54ff53a, 0x510e527f, 0x9b05688c,
                                   0x1f83d9ab, 0x5be0cd19};
  size_t offset = 0;
  while (length - offset >= 64) {
    sha256_block(state, data + offset);
    offset += 64;
  }
  std::array<uint8_t, 128> tail{};
  const size_t remaining = length - offset;
  if (remaining > 0) std::memcpy(tail.data(), data + offset, remaining);
  tail[remaining] = 0x80;
  const size_t tail_length = remaining + 9 > 64 ? 128 : 64;
  const uint64_t bit_length = static_cast<uint64_t>(length) * 8;
  for (size_t i = 0; i < 8; ++i) {
    tail[tail_length - 1 - i] = static_cast<uint8_t>(bit_length >> (8 * i));
  }
  sha256_block(state, tail.data());
  if (tail_length == 128) sha256_block(state, tail.data() + 64);
  for (size_t i = 0; i < 8; ++i) {
    out[i * 4] = static_cast<uint8_t>(state[i] >> 24);
    out[i * 4 + 1] = static_cast<uint8_t>(state[i] >> 16);
    out[i * 4 + 2] = static_cast<uint8_t>(state[i] >> 8);
    out[i * 4 + 3] = static_cast<uint8_t>(state[i]);
  }
  return 0;
}

int32_t omi_auth_random_bytes(uint8_t* out, size_t length) {
  if (out == nullptr && length != 0) return -1;
  if (length == 0) return 0;
#if defined(_WIN32)
  return BCryptGenRandom(nullptr, out, static_cast<ULONG>(length),
                         BCRYPT_USE_SYSTEM_PREFERRED_RNG) == 0
             ? 0
             : -1;
#elif defined(__APPLE__) || defined(__ANDROID__) || defined(__FreeBSD__) || \
    defined(__OpenBSD__)
  arc4random_buf(out, length);
  return 0;
#else
  size_t filled = 0;
  while (filled < length) {
    const ssize_t got = getrandom(out + filled, length - filled, 0);
    if (got < 0) {
      if (errno == EINTR) continue;
      return -1;
    }
    filled += static_cast<size_t>(got);
  }
  return 0;
#endif
}

int32_t omi_auth_callback_code(const char* callback, const char* redirect_uri,
                               const char* expected_state, char* out_code,
                               size_t out_code_capacity) {
  if (callback == nullptr || redirect_uri == nullptr ||
      expected_state == nullptr || out_code == nullptr ||
      out_code_capacity == 0) {
    return -1;
  }
  if (expected_state[0] == '\0') return 0;
  const auto received = parse_url(callback);
  const auto redirect = parse_url(redirect_uri);
  if (!received || !redirect) return 0;
  if (received->has_userinfo || received->has_fragment ||
      lowercase(received->scheme) != lowercase(redirect->scheme) ||
      received->has_authority != redirect->has_authority ||
      lowercase(received->host) != lowercase(redirect->host) ||
      received->path != redirect->path || redirect->path.empty() ||
      received->port != redirect->port) {
    return 0;
  }

  std::map<std::string, std::string> values;
  if (received->query) {
    std::string_view query = *received->query;
    size_t start = 0;
    while (start <= query.size()) {
      const size_t end = std::min(query.find('&', start), query.size());
      const std::string_view item = query.substr(start, end - start);
      const size_t equals = item.find('=');
      if (equals == std::string_view::npos) return 0;
      const auto name = percent_decode(item.substr(0, equals));
      const auto value = percent_decode(item.substr(equals + 1));
      if (!name || !value || values.count(*name) != 0) return 0;
      values.emplace(*name, *value);
      start = end + 1;
    }
  }

  const auto state = values.find("state");
  const auto code = values.find("code");
  if (values.count("error") != 0 || state == values.end() ||
      state->second != expected_state || code == values.end() ||
      code->second.empty()) {
    return 0;
  }
  if (code->second.size() + 1 > out_code_capacity) return -1;
  std::memcpy(out_code, code->second.c_str(), code->second.size() + 1);
  return 1;
}
