import 'package:integration_test/integration_test_driver.dart';

/// Drives the perf harness on a real device or simulator so `engine_frame_timing`
/// carries genuine build/raster splits (host flutter-tester cannot raster):
///
/// ```bash
/// flutter drive --profile --flavor dev \
///   --driver=test_driver/integration_test_driver.dart \
///   --target=integration_test/perf/perf_main.dart \
///   --dart-define=OMI_APP_PROFILE=local_dev -d <device>
/// ```
///
/// Budget gates may fail on a slower device; `writeResponseOnFailure` keeps the
/// scorecard (reportData.perf_scorecard) in the report either way.
Future<void> main() => integrationDriver(
      timeout: const Duration(minutes: 40),
      writeResponseOnFailure: true,
    );
