// iOS simulator acceptance: production capture/adapter/message/tutorial with
// synthetic codec, audio and response streams. This does not qualify real BLE.
import 'package:integration_test/integration_test.dart';
import '../test/widgets/pendant_tutorial_question_flow_test.dart' as scenarios;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  scenarios.main();
}
