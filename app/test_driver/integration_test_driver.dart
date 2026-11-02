import 'dart:io';

import 'package:integration_test/integration_test_driver.dart';

/// Retrieves integration reportData, including reports from failed tests.
/// For an approved physical/profile smoke use `tool/perf_device.py plan`:
///
/// ```bash
/// flutter drive --profile --flavor dev \
///   --driver=test_driver/integration_test_driver.dart \
///   --target=integration_test/perf/device_smoke_main.dart \
///   --dart-define=PERF_DEVICE_RUN_ID=<unique-run-id> \
///   --dart-define=OMI_APP_PROFILE=local_dev -d <device>
/// ```
///
/// The seeded perf_main.dart remains a host/debug harness; its synthetic auth
/// trust and host filesystem assumptions are not profile-safe. The standalone
/// smoke only verifies the profile engine/driver path, not product performance.
Future<void> main() => integrationDriver(
      timeout: const Duration(minutes: 40),
      writeResponseOnFailure: true,
      responseDataCallback: (data) => writeResponseData(
        data,
        destinationDirectory: Platform.environment['OMI_PERF_DEVICE_OUTPUT_DIR'],
      ),
    );
