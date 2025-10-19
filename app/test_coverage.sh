#!/bin/bash

echo "🧪 Running Flutter tests with coverage..."
flutter test --coverage test/backend/preferences_webhook_test.dart test/providers/developer_mode_provider_test.dart

if [ $? -eq 0 ]; then
  echo "✅ All tests passed!"
  echo ""
  echo "📊 Coverage report generated at: coverage/lcov.info"
  echo ""
  echo "To view HTML coverage report (requires lcov):"
  echo "  genhtml coverage/lcov.info -o coverage/html"
  echo "  open coverage/html/index.html"
else
  echo "❌ Some tests failed"
  exit 1
fi
