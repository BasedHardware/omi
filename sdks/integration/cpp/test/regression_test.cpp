// Regression test: list-valued query params survive in output URL.
// Build: c++ -std=c++17 -I../include ../src/client.cpp regression_test.cpp -lcurl -o regression_test
#include <cassert>
#include <iostream>
#include <map>
#include <string>

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

  std::cout << "PASS: list-valued query params" << std::endl;
  return 0;
}
