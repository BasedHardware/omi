// Mobile App Checks runs this via test.sh; release admission requires that check.
// INV-PERF-1 / #23400: production builders must participate in every scenario.
import '../../integration_test/perf/perf_main.dart' as gate;

void main() => gate.main();
