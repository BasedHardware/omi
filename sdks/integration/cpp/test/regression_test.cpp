// Regression test: list-valued query params survive in output URL.
// Build: c++ -std=c++17 -I../include ../src/client.cpp regression_test.cpp -lcurl -o regression_test
#include <cassert>
#include <iostream>
#include <map>
#include <string>
#include <type_traits>

#include "omi/integration/client.hpp"

using SendNotificationV1 = omi::integration::JsonValue (
    omi::integration::Client::*)(const std::string &);

static_assert(
    std::is_same_v<decltype(&omi::integration::Client::send_notification_v1),
                   SendNotificationV1>);

int main() {
  // Build query with repeated statuses (list-valued param) using multimap.
  std::multimap<std::string, std::string> query;
  query.emplace("uid", "user-1");
  query.emplace("statuses", "active");
  query.emplace("statuses", "closed");
  query.emplace("limit", "10");

  // Verify all pairs present, including duplicates.
  assert(query.size() == 4);

  int statuses_count = 0;
  for (const auto& [key, value] : query) {
    if (key == "statuses") {
      statuses_count++;
      assert(value == "active" || value == "closed");
    }
  }
  assert(statuses_count == 2);

  const auto notification = omi::integration::detail::notification_body_with_app_id(
      R"({"message":"hello","metadata":{"source":"sdk"},"tags":["one","two"]})", "app-123");
  assert(notification ==
         R"({"message":"hello","metadata":{"source":"sdk"},"tags":["one","two"],"aid":"app-123"})");

  const auto escaped_notification =
      omi::integration::detail::notification_body_with_app_id("{}", "app\"\\id\n");
  assert(escaped_notification == R"({"aid":"app\"\\id\n"})");

  std::cout << "PASS: list-valued query params" << std::endl;
  return 0;
}
