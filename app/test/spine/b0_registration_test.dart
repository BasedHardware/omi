import 'dart:convert';
import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/flavors.dart';
import 'package:omi/services/dev_controls/semantic_controls.dart';

import '../support/spine/contract.dart';

void main() {
  if (const String.fromEnvironment('OMI_DEV_CONTROLS') != '1') {
    test('B0 ordinary build remains ineligible', () {
      expect(semanticControlsEligible, isFalse);
    });
    return;
  }
  contractTest('B0 executes every real registration and advertises exactly its wire methods', () async {
    pendingContract('B0');
    F.env = Environment.dev;
    expect(semanticControlsEligible, isTrue);
    final handlers = <String, developer.ServiceExtensionHandler>{};
    final errors = <String>[];
    SemanticControls.instance.installIfEligible(register: (name, handler) {
      expect(handlers.containsKey(name), isFalse, reason: 'duplicate registration: $name');
      handlers[name] = handler;
      // Keep walking after a bad name: ALL production registrations must execute.
      try {
        developer.registerExtension(name, handler);
      } catch (error) {
        errors.add('$name: $error');
      }
    });
    if (errors.isNotEmpty) debugPrint('B0 SDK registration errors: ${errors.join('; ')}');
    expect(handlers, hasLength(5));
    expect(errors, isEmpty, reason: 'Dart SDK registration rejected actual production names');
    expect(handlers.keys.every((name) => name.startsWith('ext.omi.controls.')), isTrue);
    expect(handlers.keys.toSet(), {
      'ext.omi.controls.capabilities',
      'ext.omi.controls.state',
      'ext.omi.controls.wait_ready',
      'ext.omi.controls.navigate',
      'ext.omi.controls.fault',
    });
    final response = await handlers['ext.omi.controls.capabilities']!('ext.omi.controls.capabilities', {});
    final payload = jsonDecode(response.result!) as Map<String, dynamic>;
    expect(payload['contract_version'], 'semantic-controls/v1');
    final advertised = (payload['capabilities'] as List).cast<String>();
    expect(advertised.length, advertised.toSet().length);
    expect(advertised.map((name) => 'ext.omi.controls.$name').toSet(), handlers.keys.toSet());
  });
}
