import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/dev_controls/addressability.dart';

import '../support/spine/contract.dart';

class _Source implements ControlStateSource {
  @override
  AuthPhase auth = AuthPhase.signedIn;
  @override
  CapturePhase capture = CapturePhase.idle;
  @override
  BlePhase ble = BlePhase.disconnected;
  @override
  WalPhase wal = WalPhase.ready;
  @override
  int walPending = 3;
  @override
  Map<String, LoadPhase> providers = {'messages': LoadPhase.ready};
  @override
  List<FlagState> flags = [const FlagState('voice', false, false)];
  @override
  Set<String> registeredFlags = {'voice'};
  @override
  bool flagsHydrated = true;
}

class _Navigator implements AddressableNavigator {
  @override
  String? visibleRoute = 'chat';
  @override
  bool rootMounted = true;
  @override
  int pendingTransitions = 0;
  @override
  Future<void> navigate(String routeId, {String? recordId}) async => throw StateError('projection must not navigate');
}

void main() {
  contractTest('B1 snapshot exact allowlist, fresh state, bounded counts and unavailable providers', () {
    pendingContract('B1');
    final source = _Source();
    final navigation = _Navigator();
    final controls = ControlsV2(source, navigation);
    expect(controls.snapshot(), {
      'contract_version': 'semantic-controls/v2',
      'route': 'chat',
      'auth': 'signedIn',
      'capture': 'idle',
      'ble': 'disconnected',
      'wal': 'ready',
      'wal_pending': 3,
      'providers': {
        'messages': 'ready',
        'conversations': 'unavailable',
        'memories': 'unavailable',
        'tasks': 'unavailable'
      },
      'flags': [
        {'id': 'voice', 'effective': false, 'override': false}
      ],
      'flags_hydrated': true,
      'readiness': {'signedIn': true, 'routed': true, 'captureIdle': true, 'appReady': true},
    });
    final before = jsonEncode(controls.snapshot());
    source.auth = AuthPhase.reauthentication;
    source.walPending = 5000;
    source.flags = [const FlagState('voice', true, null)];
    navigation.visibleRoute = null;
    final after = controls.snapshot();
    expect(after['auth'], 'reauthentication');
    expect(after['wal_pending'], 1000);
    expect(after['route'], isNull);
    expect(after['flags'], [
      {'id': 'voice', 'effective': true, 'override': null}
    ]);
    expect(jsonEncode(after), isNot(before));
    source.wal = WalPhase.unavailable;
    expect(controls.snapshot()['wal_pending'], isNull);
  });

  for (final failure in ['auth', 'capture', 'ble', 'wal', 'provider', 'flags', 'root', 'transition', 'route']) {
    contractTest('B1 readiness closes on $failure, then recovers without stale cached success', () async {
      pendingContract('B1');
      final source = _Source();
      final nav = _Navigator();
      final controls = ControlsV2(source, nav);
      expect((controls.snapshot()['readiness'] as Map)['appReady'], isTrue);
      switch (failure) {
        case 'auth':
          source.auth = AuthPhase.cuttingOver;
        case 'capture':
          source.capture = CapturePhase.unavailable;
        case 'ble':
          source.ble = BlePhase.connecting;
        case 'wal':
          source.wal = WalPhase.failed;
        case 'provider':
          source.providers = {};
        case 'flags':
          source.flagsHydrated = false;
        case 'root':
          nav.rootMounted = false;
        case 'transition':
          nav.pendingTransitions = 1;
        case 'route':
          nav.visibleRoute = 'unregistered';
      }
      expect((controls.snapshot()['readiness'] as Map)['appReady'], isFalse);
      if (failure == 'route') expect(controls.snapshot()['route'], isNull);
      await expectLater(controls.waitReady('appReady', timeout: const Duration(milliseconds: 1)),
          throwsA(isA<ControlReadinessTimeout>()));
      source.auth = AuthPhase.signedIn;
      source.capture = CapturePhase.idle;
      source.ble = BlePhase.disconnected;
      source.wal = WalPhase.ready;
      source.providers = {'messages': LoadPhase.ready};
      source.flagsHydrated = true;
      nav.rootMounted = true;
      nav.pendingTransitions = 0;
      nav.visibleRoute = 'chat';
      final state = await controls.waitReady('appReady', timeout: const Duration(milliseconds: 20));
      expect((state['readiness'] as Map)['appReady'], isTrue);
    });
  }

  contractTest('B1 rejects arbitrary provider/flag payloads instead of leaking them', () {
    pendingContract('B1');
    final source = _Source();
    final controls = ControlsV2(source, _Navigator());
    // Establish that this is an implemented projection before negative assertions.
    expect(controls.snapshot()['route'], 'chat');
    source.providers = {'transcript-secret': LoadPhase.ready};
    expect(controls.snapshot, throwsArgumentError);
    source.providers = {};
    source.flags = [const FlagState('email-secret@example.test', true, null)];
    expect(controls.snapshot, throwsArgumentError);
    source.flags = List.generate(65, (i) => FlagState('f$i', true, null));
    source.registeredFlags = source.flags.map((f) => f.id).toSet();
    expect(controls.snapshot, throwsArgumentError);
    source.registeredFlags = {'voice'};
    source.flags = [const FlagState('voice', true, null), const FlagState('voice', false, false)];
    expect(controls.snapshot, throwsArgumentError);
    source.registeredFlags = {'secret@example.test'};
    source.flags = [const FlagState('secret@example.test', true, null)];
    expect(controls.snapshot, throwsArgumentError);
    source.flags = [];
    source.walPending = -1;
    expect(controls.snapshot, throwsArgumentError);
  });

  contractTest('B1 negotiation preserves v1 default and rejects unknown versions/actions', () {
    pendingContract('B1');
    final controls = ControlsV2(_Source(), _Navigator());
    expect(controls.capabilities()['contract_version'], 'semantic-controls/v1');
    final v2 = controls.capabilities(requestedVersion: 'semantic-controls/v2');
    expect(v2['contract_version'], 'semantic-controls/v2');
    expect(v2['supported_versions'], ['semantic-controls/v1', 'semantic-controls/v2']);
    expect(v2['capabilities'], unorderedEquals(['capabilities', 'state', 'wait_ready', 'navigate', 'fault']));
    expect(v2['readiness'], unorderedEquals(['signedIn', 'routed', 'captureIdle', 'appReady']));
    expect(() => controls.capabilities(requestedVersion: 'semantic-controls/v99'), throwsArgumentError);
  });

  contractTest('B1 deadline and predicate validation is bounded', () async {
    pendingContract('B1');
    final controls = ControlsV2(_Source(), _Navigator());
    expect(controls.snapshot()['route'], 'chat');
    for (final duration in [Duration.zero, const Duration(seconds: 31)]) {
      await expectLater(controls.waitReady('appReady', timeout: duration), throwsArgumentError);
    }
    await expectLater(controls.waitReady('invented', timeout: const Duration(seconds: 1)), throwsArgumentError);
  });
}
