// Runs the production recording-detail failure/retry regressions in a native
// Flutter runtime. Only the SyncProvider dependency is synthetic; no account,
// microphone, network transfer, or customer recordings are used.
import 'package:integration_test/integration_test.dart';

import '../test/pages/conversations/wal_item_detail_recovery_test.dart' as regression;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  regression.main();
}
