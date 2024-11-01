#!/bin/bash

# Function to run tests with proper output formatting
run_test() {
    echo "🧪 Running tests for: $1"
    flutter test "$1" --coverage --reporter expanded
}

# Main test execution
echo "🚀 Starting test suite..."

# Run build_runner first to generate mocks
echo "🔨 Generating mocks..."
dart run build_runner build --delete-conflicting-outputs

# Run the tests
run_test "test/app_test.dart"

# Check exit code
if [ $? -eq 0 ]; then
    echo "✅ Tests completed successfully!"

    # Generate coverage report if lcov is installed
    if command -v lcov >/dev/null 2>&1; then
        echo "📊 Generating coverage report..."
        genhtml coverage/lcov.info -o coverage/html
        echo "Coverage report generated in coverage/html"
    fi
else
    echo "❌ Tests failed!"
    exit 1
fi
