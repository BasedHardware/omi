#!/bin/bash

echo "🚀 Starting test suite..."

# Clean and rebuild mocks
echo "🔨 Generating mocks..."
dart run build_runner build --delete-conflicting-outputs

# Function to run tests with proper output formatting
run_test() {
    echo "🧪 Running tests for: $1"
    flutter test "$1" --coverage
}

# Run all test files
echo "📋 Running all tests..."

# Core tests
run_test "test/app_test.dart"

# Provider tests
run_test "test/providers/auth_provider_test.dart"
run_test "test/providers/capture_provider_test.dart"
run_test "test/providers/memory_provider_test.dart"
run_test "test/providers/message_provider_test.dart"

# Service tests
run_test "test/services/device_connection_test.dart"
run_test "test/services/notifications_test.dart"

# Backend tests
run_test "test/backend/schema/message_test.dart"

# Combine coverage data
if [ -d "coverage" ]; then
    echo "📊 Generating combined coverage report..."
    lcov --add-tracefile coverage/lcov.info -o coverage/lcov.info
    genhtml coverage/lcov.info -o coverage/html
    echo "Coverage report generated in coverage/html"
fi

# Check if any test failed
if [ $? -eq 0 ]; then
    echo "✅ All tests completed successfully!"
else
    echo "❌ Some tests failed!"
    exit 1
fi
