#include "omi_auth.h"

#include <cstdio>
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

static std::string sha256_hex(const std::string& input) {
  uint8_t digest[OMI_AUTH_SHA256_LENGTH];
  if (omi_auth_sha256(reinterpret_cast<const uint8_t*>(input.data()),
                      input.size(), digest) != 0) {
    return "";
  }
  std::string hex;
  char byte[3];
  for (uint8_t value : digest) {
    std::snprintf(byte, sizeof(byte), "%02x", value);
    hex += byte;
  }
  return hex;
}

static void test_sha256() {
  expect(sha256_hex("") ==
             "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
         "empty");
  expect(sha256_hex("abc") ==
             "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
         "abc");
  expect(sha256_hex("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq") ==
             "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
         "two blocks");
  expect(sha256_hex(std::string(64, 'a')) ==
             "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb",
         "exact block");
  expect(sha256_hex(std::string(1000000, 'a')) ==
             "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0",
         "million a");
  uint8_t digest[OMI_AUTH_SHA256_LENGTH];
  expect(omi_auth_sha256(nullptr, 1, digest) == -1, "null data");
  expect(omi_auth_sha256(nullptr, 0, nullptr) == -1, "null out");
}

static void test_random_bytes() {
  uint8_t first[32] = {};
  uint8_t second[32] = {};
  expect(omi_auth_random_bytes(first, sizeof(first)) == 0, "random ok");
  expect(omi_auth_random_bytes(second, sizeof(second)) == 0, "random ok again");
  expect(std::memcmp(first, second, sizeof(first)) != 0, "random differs");
  expect(omi_auth_random_bytes(nullptr, 1) == -1, "random null");
  expect(omi_auth_random_bytes(nullptr, 0) == 0, "random empty");
}

static std::string code_of(const char* callback, const char* redirect,
                           const char* state) {
  char out[256];
  const int32_t result =
      omi_auth_callback_code(callback, redirect, state, out, sizeof(out));
  return result == 1 ? std::string(out) : std::string("<nil>");
}

static void test_callback_code() {
  const char* loopback = "http://127.0.0.1:19500/callback";
  const char* app = "omi-rnruntime://auth/callback";

  expect(code_of("http://127.0.0.1:19500/callback?code=xyz&state=st", loopback,
                 "st") == "xyz",
         "loopback");
  expect(code_of("http://127.0.0.1:19500/callback?code=loopback%2Bcode&state=st",
                 loopback, "st") == "loopback+code",
         "decoded plus");
  expect(code_of("omi-rnruntime://auth/callback?code=app-code&state=st"
                 "&scope=email%20profile&authuser=0&prompt=consent",
                 app, "st") == "app-code",
         "app scheme with extras");
  expect(code_of("http://127.0.0.1:19500/callback?code=a%2Bb%2F%3D&state=st",
                 loopback, "st") == "a+b/=",
         "decoded escapes");
  expect(code_of("HTTP://127.0.0.1:19500/callback?code=x&state=st", loopback,
                 "st") == "x",
         "scheme case");
  expect(code_of("omi-rnruntime://auth/callback?code=a1&state=s2", app, "s2") ==
             "a1",
         "app scheme");

  const char* rejected_loopback[] = {
      "http://user@127.0.0.1:19500/callback?code=x&state=st",
      "http://127.0.0.1:19500/callback?code=xyz&state=other",
      "http://127.0.0.1:19500/callback?state=st",
      "http://127.0.0.1:19500/callback?code=x&state=st#frag",
      "http://127.0.0.1:19500/callback?code=x&state=st#",
      "http://127.0.0.1:19999/callback?code=x&state=st",
      "http://127.0.0.1/callback?code=x&state=st",
      "http://127.0.0.1:19500/callback/?code=x&state=st",
      "not a url",
      "",
      "http://127.0.0.1:19500/callback?code=%00x&state=st",
      "http://127.0.0.1:19500/callback?code=%FFx&state=st",
      "http://127.0.0.1:19500/callback?code=%zz&state=st",
      "http://127.0.0.1:19500/callback?code=&state=st",
      "http://127.0.0.1:19500/callback?code=x&state=st&",
  };
  for (const char* callback : rejected_loopback) {
    expect(code_of(callback, loopback, "st") == "<nil>", callback);
  }

  const char* rejected_app[] = {
      "https://auth/callback?code=x&state=st",
      "omi-rnruntime://auth/callback?code=x&code=y&state=st",
      "omi-rnruntime://auth/callback?code=x&state=st&state=st",
      "omi-rnruntime://auth/callback?code=x&state=st&%73tate=other",
      "omi-rnruntime://auth/callback?code=x&state=st&state",
      "omi-rnruntime://auth/callback?code=x&state=st&extra=a&extra=b",
      "omi-rnruntime://auth/callback?code=x&state=st&extra",
      "omi-rnruntime://auth/%63allback?code=x&state=st",
      "omi-rnruntime://user@auth/callback?code=x&state=st",
      "omi-rnruntime://user:password@auth/callback?code=x&state=st",
      "omi-rnruntime://auth/callback?code=x&state=st&error=access_denied",
      "omi-rnruntime://auth/callback?code=x&state=st&error=",
      "omi-rnruntime://evil/callback?code=x&state=st",
  };
  for (const char* callback : rejected_app) {
    expect(code_of(callback, app, "st") == "<nil>", callback);
  }
  expect(code_of("omi-rnruntime://auth/callback?code=x&state=", app, "") ==
             "<nil>",
         "empty expected state");
  expect(code_of("http://127.0.0.1:19500?code=x&state=st",
                 "http://127.0.0.1:19500", "st") == "<nil>",
         "empty redirect path");

  char small[2];
  expect(omi_auth_callback_code("omi-rnruntime://auth/callback?code=xy&state=st",
                                app, "st", small, sizeof(small)) == -1,
         "small buffer");
  expect(omi_auth_callback_code(nullptr, app, "st", small, sizeof(small)) == -1,
         "null callback");
}

int main() {
  test_sha256();
  test_random_bytes();
  test_callback_code();
  if (failures != 0) {
    std::cerr << failures << " failure(s)\n";
    return 1;
  }
  std::cout << "omi_auth: all tests passed\n";
  return 0;
}
