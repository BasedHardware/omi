import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import '../support/spine/contract.dart';

// Static adoption tripwires complement the behavioral owner/provider tests.
// They prevent a builder from shipping an unused owner beside old global actors.
String code(String path) => File(path)
    .readAsStringSync()
    .replaceAll(RegExp(r'''//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*' '''.trim()), ' ');

Iterable<String> captureImplementation() sync* {
  final pending = ['lib/services/capture/capture_controller.dart', 'lib/providers/capture_provider.dart'];
  final seen = <String>{};
  while (pending.isNotEmpty) {
    final path = pending.removeLast();
    if (!seen.add(path) || !File(path).existsSync()) continue;
    yield path;
    final source = File(path).readAsStringSync();
    for (final match in RegExp(r"import 'package:omi/([^']*capture[^']*\.dart)'").allMatches(source)) {
      final dependency = 'lib/${match.group(1)}';
      // Follow capture-owned extraction files; pre-existing STT policy/cache
      // adapters have their own migration scope, not capture ownership.
      final filename = dependency.split('/').last;
      if (filename.startsWith('capture_') &&
          !dependency.endsWith('capture_composition.dart') &&
          !dependency.endsWith('capture_seams.dart')) {
        pending.add(dependency);
      }
    }
  }
}

void main() {
  contractTest('C1 exemplar has no singleton escape or implicit production connectivity', () {
    pendingContract('C1');
    final global = RegExp(r'SharedPreferencesUtil\s*\(|ServiceManager\s*\.\s*instance|'
        r'PlatformManager\s*\.\s*instance|AuthService\s*\.\s*instance|BleBridge\s*\.\s*instance|'
        r'RecordingTransferCoordinator\s*\.\s*instance|ForegroundUtil\s*\.|'
        r'CaptureConnectivityBoundary\s*\.\s*production|CaptureAuthBoundary\s*\.\s*production');
    for (final path in captureImplementation()) {
      expect(global.allMatches(code(path)).map((m) => m.group(0)), isEmpty, reason: path);
    }
  });
  contractTest('C1 capture requester and extracted code relinquish singleton coordinator access', () {
    pendingContract('C1');
    final violations = <String>[];
    final wake = RegExp(r'RecordingTransferCoordinator\s*\.\s*instance');
    for (final path in captureImplementation()) {
      if (wake.hasMatch(code(path))) violations.add(path);
    }
    expect(violations, isEmpty);
  });
  contractTest('C1 capture and extracted code request FGS intent rather than acting independently', () {
    final actor =
        RegExp(r'ForegroundUtil\s*\.\s*(?:initializeForegroundService|startForegroundTask|stopForegroundTask)\s*\(');
    for (final path in captureImplementation()) {
      expect(actor.allMatches(code(path)), isEmpty, reason: path);
    }
  });
}
