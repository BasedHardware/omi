#!/bin/bash
set -euo pipefail

# Initialize exit code
EXIT_CODE=0

# Check if required commands are available
command -v dart >/dev/null 2>&1 || { echo "❌ dart is required but not installed. Aborting." >&2; exit 1; }
command -v flutter >/dev/null 2>&1 || { echo "❌ flutter is required but not installed. Aborting." >&2; exit 1; }

echo "🚀 Starting test suite..."

# Function to run tests with proper output formatting
run_test() {
    local test_file="$1"
    echo "🧪 Running tests for: $test_file"

    if [ ! -f "$test_file" ]; then
        echo "❌ Test file not found: $test_file"
        return 1
    fi

    if flutter test "$test_file" --coverage; then
        echo "✅ Test passed: $test_file"
        return 0
    else
        echo "❌ Test failed: $test_file"
        EXIT_CODE=1
        return 1
    fi
}

# Clean and rebuild mocks
echo "🔨 Generating mocks..."
dart run build_runner build --delete-conflicting-outputs

# Run working tests
echo "📋 Running tests..."

# Schema tests
echo "📦 Running schema tests..."
run_test "test/backend/schema/message_test.dart"

# Provider tests
echo "📦 Running provider tests..."
run_test "test/providers/capture_provider_test.dart"
run_test "test/providers/memory_provider_test.dart"

# Service tests
echo "📦 Running service tests..."
run_test "test/services/device_connection_test.dart"

# Generate coverage report if tests passed
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ All tests completed successfully!"

    if [ -d "coverage" ] && command -v lcov >/dev/null 2>&1; then
        echo "📊 Generating coverage report..."
        lcov -a coverage/lcov.info -o coverage/lcov_combined.info
        genhtml coverage/lcov_combined.info -o coverage/html
        echo "Coverage report generated in coverage/html"
    fi
else
    echo "❌ Some tests failed!"
fi

exit $EXIT_CODE
