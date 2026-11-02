// Mobile App Checks runs this via test.sh; release admission requires that check.
// INV-PERF-1 / #23400: production builders must participate in every scenario.
import 'package:flutter_test/flutter_test.dart';
import '../../integration_test/perf/perf_main.dart' as gate;

void main() {
  // CI amortizes compilation across three independently seeded trials. The
  // local runner selects one inner trial in each of three fresh processes.
  const repeats = int.fromEnvironment('PERF_GATE_INNER_REPEATS', defaultValue: 3);
  if (repeats < 1 || repeats > 3) throw StateError('PERF_GATE_INNER_REPEATS must be 1..3');
  for (var trial = 1; trial <= repeats; trial++) {
    group('trial $trial', gate.main);
  }
}
