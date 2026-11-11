import 'dart:convert';
import 'dart:developer' as developer;

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/flavors.dart';
import 'package:omi/services/dev_controls/semantic_controls.dart';

import '../support/spine/contract.dart';

void main() {
  if (const String.fromEnvironment('OMI_DEV_CONTROLS') != '1') {
    test('B1 ordinary build exposes no wire handlers', () {
      SemanticControls.instance.installIfEligible(register: (_, __) => fail('ineligible registrar invoked'));
      expect(SemanticControls.instance.installed, isFalse);
    });
    return;
  }
  contractTest('B1 v2 is served by actual registered handlers; legacy omission stays v1', () async {
    pendingContract('B1');
    F.env = Environment.dev;
    final handlers = <String, developer.ServiceExtensionHandler>{};
    expect(
        () => SemanticControls.instance.installIfEligible(register: (name, handler) {
              developer.registerExtension(name, handler);
              handlers[name] = handler;
            }),
        returnsNormally);
    final capability = handlers['ext.omi.controls.capabilities']!;
    final legacy = jsonDecode((await capability('ext.omi.controls.capabilities', {})).result!) as Map;
    expect(legacy['contract_version'], 'semantic-controls/v1');
    final v2 =
        jsonDecode((await capability('ext.omi.controls.capabilities', {'version': 'semantic-controls/v2'})).result!)
            as Map;
    expect(v2['contract_version'], 'semantic-controls/v2');
    expect((v2['capabilities'] as List).map((x) => 'ext.omi.controls.$x').toSet(), handlers.keys.toSet());
    final unknown = await capability('ext.omi.controls.capabilities', {'version': 'semantic-controls/v99'});
    expect(unknown.isError(), isTrue);
    final state = jsonDecode(
        (await handlers['ext.omi.controls.state']!('ext.omi.controls.state', {'version': 'semantic-controls/v2'}))
            .result!) as Map;
    expect(
        state.keys,
        unorderedEquals([
          'contract_version',
          'route',
          'auth',
          'capture',
          'ble',
          'wal',
          'wal_pending',
          'providers',
          'flags',
          'flags_hydrated',
          'readiness'
        ]));
    expect((state['readiness'] as Map)['appReady'], isFalse, reason: 'no app/provider scope is mounted in this test');
  });
}
