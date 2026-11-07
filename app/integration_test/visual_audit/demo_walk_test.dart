// Booted demo walk. Record it with app/scripts/demo_walk.sh. This file is not part of test.sh.
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:omi/backend/preferences.dart';

import '../journeys/support/hermetic_boot.dart';
import 'demo_billing.dart';
import 'harness.dart';
import 'registry.dart';
import 'walks.dart';

void main() {
  // QuietWalkBinding is created by flutter_test_config.dart before this main. Re-asserting the
  // flags here would trip the binding's start-of-test snapshot if the test body changed them.
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  final walk = demoWalkById(Platform.environment['OMI_DEMO_WALK'] ?? uiCleanupWalk.id);

  testWidgets('demo walk ${walk.id}', (tester) async {
    auditWalkMode = true;
    HttpOverrides.global = LoopbackOnly();
    // The booted app's capture-policy channel is not part of this walk. A revision of 1 keeps
    // hermetic boot from writing an unmute the plugin would reject.
    SharedPreferencesUtil.capturePolicyBridgeForTesting = (method, _) async => method == 'getRevision' ? 1 : null;
    final server = await tester.runAsync(() => JourneyHermeticBoot.start());
    addTearDown(() async {
      await server?.stop();
      SharedPreferencesUtil.capturePolicyBridgeForTesting = null;
    });
    await loadAuditFonts();
    final suite = AuditSuite(
      name: 'demo-walk',
      scenarios: auditSuite.scenarios,
      providers: demoAuditProviders,
      theme: auditSuite.theme,
      hostBackground: auditSuite.hostBackground,
    );
    await playDemoWalk(tester: tester, suite: suite, walk: walk);
    walkLog('DEMO_WALK_DONE');
    await Future<void>.delayed(const Duration(seconds: 1));
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  });
}
