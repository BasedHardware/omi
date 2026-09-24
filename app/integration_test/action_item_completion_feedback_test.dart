import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:omi/backend/preferences.dart';

import '../test/widgets/action_item_completion_feedback_test.dart' as feedback;

// Run the real Tasks and Chat controls on a device with synthetic task writes.
// This checks iOS UI behavior; it does not exercise production auth or the API.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  // This task-only fixture has no native capture session.
  setUpAll(() {
    SharedPreferencesUtil.capturePolicyBridgeForTesting = (method, arguments) async => switch (method) {
          'getRevision' => 0,
          'setMuted' => null,
          _ => throw UnsupportedError(method),
        };
  });
  tearDownAll(() => SharedPreferencesUtil.capturePolicyBridgeForTesting = null);
  feedback.main();
}
