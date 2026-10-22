import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import '../../test/perf/sync_indicator_isolation_test.dart' as scenarios;

/// Same counters and workload as the regression suite, using explicit live
/// frame pumps. Host UI pipeline times exclude GPU raster and are diagnostic.
void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.onlyPumps;
  scenarios.main();
}
