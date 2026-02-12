import 'package:integration_test/integration_test_driver.dart';

/// Performance test driver
///
/// This driver collects timeline data and writes performance summaries.
/// Use with any of the performance_*.dart integration tests.
///
/// Usage:
/// ```bash
/// flutter drive \
///   --driver=test_driver/perf_test_driver.dart \
///   --target=integration_test/performance_memory_test.dart \
///   --profile \
///   --flavor dev \
///   -d <device_id>
/// ```
Future<void> main() {
  return integrationDriver(
    responseDataCallback: (data) async {
      // The integration tests write their own JSON results to /tmp/.
      // This callback can be extended to aggregate data if needed.
      if (data != null) {
        print('Performance test data received: ${data.keys.join(', ')}');
      }
    },
  );
}
