#!/bin/bash

echo "🚀 Starting test suite..."

# Initialize exit code
EXIT_CODE=0

# Clean and rebuild mocks
echo "🔨 Generating mocks..."
dart run build_runner build --delete-conflicting-outputs

# Function to run tests with proper output formatting
run_test() {
    echo "🧪 Running tests for: $1"
    if flutter test "$1" --coverage; then
        echo "✅ Test passed: $1"
    else
        echo "❌ Test failed: $1"
        EXIT_CODE=1
    fi
}

# Run all test files
echo "📋 Running all tests..."

# Core tests
run_test "test/app_test.dart"
run_test "test/providers/auth_provider_test.dart"
run_test "test/providers/capture_provider_test.dart"
run_test "test/providers/memory_provider_test.dart"
run_test "test/services/device_connection_test.dart"
run_test "test/services/notifications_test.dart"
run_test "test/backend/schema/message_test.dart"

# Generate coverage report if all tests passed
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ All tests completed successfully!"

    if [ -d "coverage" ]; then
        echo "📊 Generating coverage report..."
        lcov -a coverage/lcov.info -o coverage/lcov_combined.info
        genhtml coverage/lcov_combined.info -o coverage/html
        echo "Coverage report generated in coverage/html"
    fi
else
    echo "❌ Some tests failed!"
fi

exit $EXIT_CODE
