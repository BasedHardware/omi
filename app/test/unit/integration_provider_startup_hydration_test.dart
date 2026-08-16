import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  // Static tripwire, not behavioral coverage: signed-in startup must hydrate
  // IntegrationProvider the same way it hydrates TaskIntegrationProvider.
  test('signed-in startup loads IntegrationProvider (static tripwire)', () {
    final source = File('lib/core/app_shell.dart').readAsStringSync();
    expect(
      source.contains('context.read<IntegrationProvider>().loadFromBackend();'),
      isTrue,
    );
    expect(
      source.contains('context.read<TaskIntegrationProvider>().loadFromBackend();'),
      isTrue,
    );
  });
}
