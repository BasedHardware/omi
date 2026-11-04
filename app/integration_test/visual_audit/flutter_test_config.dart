import 'dart:async';

import 'quiet_walk_binding.dart';

/// Installed before the test runner's IntegrationTestWidgetsFlutterBinding.ensureInitialized,
/// so the walk uses [QuietWalkBinding] instead of the binding that paints the tap crosshair.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  QuietWalkBinding();
  await testMain();
}
