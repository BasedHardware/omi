import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import '../support/spine/contract.dart';

// Static adoption tripwires complement the behavioral owner/provider tests.
// They prevent a builder from shipping an unused owner beside old global actors.
String code(String path) => File(path)
    .readAsStringSync()
    .replaceAll(RegExp(r'''//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*' '''.trim()), ' ');

void main() {
  contractTest('C1 exemplar has no singleton escape or implicit production connectivity', () {
    pendingContract('C1');
    final global = RegExp(r'SharedPreferencesUtil\s*\(|ServiceManager\s*\.\s*instance|'
        r'PlatformManager\s*\.\s*instance|AuthService\s*\.\s*instance|BleBridge\s*\.\s*instance|'
        r'RecordingTransferCoordinator\s*\.\s*instance|ForegroundUtil\s*\.|'
        r'CaptureConnectivityBoundary\s*\.\s*production|CaptureAuthBoundary\s*\.\s*production');
    for (final path in ['lib/services/capture/capture_controller.dart', 'lib/providers/capture_provider.dart']) {
      expect(global.allMatches(code(path)).map((m) => m.group(0)), isEmpty, reason: path);
    }
  });
  contractTest('C1 all five requester classes relinquish singleton coordinator wake', () {
    pendingContract('C1');
    final violations = <String>[];
    final wake = RegExp(r'\.\s*instance\s*\.\s*wake\s*\(');
    for (final file in Directory('lib').listSync(recursive: true).whereType<File>()) {
      if (file.path.endsWith('.dart') && wake.hasMatch(code(file.path))) violations.add(file.path);
    }
    expect(violations, isEmpty);
  });
  contractTest('C1 Home and controller request FGS intent rather than acting independently', () {
    pendingContract('C1');
    final actor =
        RegExp(r'ForegroundUtil\s*\.\s*(?:initializeForegroundService|startForegroundTask|stopForegroundTask)\s*\(');
    for (final path in ['lib/pages/home/page.dart', 'lib/services/capture/capture_controller.dart']) {
      expect(actor.allMatches(code(path)), isEmpty, reason: path);
    }
  });
}
