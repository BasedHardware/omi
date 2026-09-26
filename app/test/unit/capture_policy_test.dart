import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
// The legacy shared_preferences test API does not expose its platform store;
// use the already-transitive interface to exercise false/ordered writes.
// ignore: depend_on_referenced_packages
import 'package:shared_preferences_platform_interface/shared_preferences_platform_interface.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/capture/capture_policy.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(() {
    SharedPreferencesUtil.capturePolicyBridgeForTesting = null;
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  test('fixture parsing is strict and fail closed', () async {
    final fixture = jsonDecode(await File('test/fixtures/capture_policy.json').readAsString()) as Map<String, dynamic>;
    final cases = fixture['cases'] as List<dynamic>;

    for (final rawCase in cases) {
      final testCase = rawCase as Map<String, dynamic>;
      final encoded = testCase['policy'] as String?;
      final expectedMuted = testCase['expectedMuted'] as bool;
      final expectedRevision = testCase['expectedRevision'] as int;

      final parsed = encoded == null
          ? CapturePolicy.fromLegacy(
              deviceMuted: testCase['deviceMuted'] as bool,
              batchMuted: testCase['batchMuted'] as bool,
            )
          : CapturePolicy.tryParse(encoded);
      if (parsed == null) {
        expect(expectedMuted, isTrue, reason: testCase['name'] as String);
        expect(expectedRevision, 0, reason: testCase['name'] as String);
      } else {
        expect(parsed.muted, expectedMuted, reason: testCase['name'] as String);
        expect(parsed.revision, expectedRevision, reason: testCase['name'] as String);
      }
    }
  });

  test('initialization migrates legacy flags and removes them after persistence', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'deviceMuted': false,
      'batchMuted': true,
    });

    await SharedPreferencesUtil.init();
    final prefs = await SharedPreferences.getInstance();

    expect(SharedPreferencesUtil().capturePolicy, const CapturePolicy(revision: 0, muted: true));
    expect(jsonDecode(prefs.getString(SharedPreferencesUtil.capturePolicyKey)!), <String, dynamic>{
      'version': 1,
      'revision': 0,
      'muted': true,
    });
    expect(prefs.containsKey('deviceMuted'), isFalse);
    expect(prefs.containsKey('batchMuted'), isFalse);
  });

  test('canonical policy takes precedence over stale legacy flags', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      SharedPreferencesUtil.capturePolicyKey: '{"version":1,"revision":4,"muted":false}',
      'deviceMuted': true,
      'batchMuted': true,
    });

    await SharedPreferencesUtil.init();
    final prefs = await SharedPreferences.getInstance();

    expect(SharedPreferencesUtil().capturePolicy, const CapturePolicy(revision: 4, muted: false));
    expect(prefs.containsKey('deviceMuted'), isFalse);
    expect(prefs.containsKey('batchMuted'), isFalse);
  });

  test('malformed canonical policy fails closed and is repaired', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      SharedPreferencesUtil.capturePolicyKey: '{"version":2,"revision":8,"muted":false}',
      'deviceMuted': false,
      'batchMuted': false,
    });

    await SharedPreferencesUtil.init();
    final prefs = await SharedPreferences.getInstance();

    expect(SharedPreferencesUtil().capturePolicy, const CapturePolicy(revision: 0, muted: true));
    expect(prefs.getString(SharedPreferencesUtil.capturePolicyKey), '{"version":1,"revision":0,"muted":true}');
    expect(prefs.containsKey('deviceMuted'), isFalse);
    expect(prefs.containsKey('batchMuted'), isFalse);
  });

  test('mute publishes synchronously and unmute waits for persistence', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      SharedPreferencesUtil.capturePolicyKey: '{"version":1,"revision":0,"muted":false}',
    });
    await SharedPreferencesUtil.init();
    final prefs = SharedPreferencesUtil();

    final mute = prefs.setCaptureMuted(true);
    expect(prefs.capturePolicy, const CapturePolicy(revision: 1, muted: true));
    expect(await mute, const CapturePolicy(revision: 1, muted: true));

    final unmute = prefs.setCaptureMuted(false);
    expect(prefs.capturePolicy, const CapturePolicy(revision: 1, muted: true));
    expect(await unmute, const CapturePolicy(revision: 2, muted: false));
    expect(prefs.capturePolicy, const CapturePolicy(revision: 2, muted: false));
  });

  test('native bridge re-acknowledges the loaded durable policy', () async {
    final calls = <String>[];
    SharedPreferencesUtil.capturePolicyBridgeForTesting = (method, arguments) async {
      calls.add('$method:${arguments['revision']}:${arguments['muted']}');
      return method == 'getRevision' ? 3 : true;
    };
    SharedPreferences.setMockInitialValues(<String, Object>{
      SharedPreferencesUtil.capturePolicyKey: '{"version":1,"revision":3,"muted":true}',
    });

    await SharedPreferencesUtil.init();

    expect(calls, <String>['getRevision:null:null', 'setMuted:3:true']);
  });

  test('serialized writes keep a newer mute from being overwritten by a stale unmute', () async {
    final store = _GatedPreferencesStore(<String, Object>{
      'flutter.capturePolicy': '{"version":1,"revision":0,"muted":false}',
    });
    await _initWithStore(store);
    final prefs = SharedPreferencesUtil();

    final mute = prefs.setCaptureMuted(true);
    await store.waitForWrite(1);
    final unmute = prefs.setCaptureMuted(false);
    expect(prefs.capturePolicy, const CapturePolicy(revision: 1, muted: true));

    store.releaseNextWrite();
    await store.waitForWrite(2);
    expect(prefs.capturePolicy, const CapturePolicy(revision: 1, muted: true));
    store.releaseNextWrite();

    expect(await mute, const CapturePolicy(revision: 1, muted: true));
    expect(await unmute, const CapturePolicy(revision: 2, muted: false));
    expect(prefs.capturePolicy, const CapturePolicy(revision: 2, muted: false));
  });

  test('stale unmute does not release a newer native mute latch', () async {
    final calls = <String>[];
    SharedPreferencesUtil.capturePolicyBridgeForTesting = (method, arguments) async {
      if (method == 'getRevision') return 0;
      calls.add('$method:${arguments['revision']}:${arguments['muted']}');
      return true;
    };
    final store = _GatedPreferencesStore(<String, Object>{
      'flutter.capturePolicy': '{"version":1,"revision":0,"muted":false}',
    });
    await _initWithStore(store);
    final prefs = SharedPreferencesUtil();

    final unmute = prefs.setCaptureMuted(false);
    await store.waitForWrite(1);
    final mute = prefs.setCaptureMuted(true);
    store.releaseNextWrite();
    await store.waitForWrite(2);
    store.releaseNextWrite();
    await unmute;
    await mute;

    expect(calls, <String>['setMuted:0:false', 'setMuted:2:true']);
  });

  test('native unmute failure rolls durable policy back to muted', () async {
    SharedPreferencesUtil.capturePolicyBridgeForTesting = (method, arguments) async {
      if (method == 'getRevision') return 4;
      if (arguments['muted'] == false) throw StateError('native latch rejected release');
      return true;
    };
    SharedPreferences.setMockInitialValues(<String, Object>{
      SharedPreferencesUtil.capturePolicyKey: '{"version":1,"revision":4,"muted":true}',
    });
    await SharedPreferencesUtil.init();
    final prefs = SharedPreferencesUtil();

    await expectLater(prefs.setCaptureMuted(false), throwsStateError);
    expect(prefs.capturePolicy, const CapturePolicy(revision: 6, muted: true));
    final stored = await SharedPreferences.getInstance();
    expect(stored.getString(SharedPreferencesUtil.capturePolicyKey), '{"version":1,"revision":6,"muted":true}');
  });

  test('failed mute persistence retains native denial and surfaces the error', () async {
    var nativeMuted = false;
    SharedPreferencesUtil.capturePolicyBridgeForTesting = (method, arguments) async {
      if (method == 'getRevision') return 4;
      nativeMuted = arguments['muted'] as bool;
      return true;
    };
    final store = _GatedPreferencesStore(<String, Object>{
      'flutter.capturePolicy': '{"version":1,"revision":4,"muted":false}',
    })
      ..failWrites = true;
    await _initWithStore(store);

    await expectLater(SharedPreferencesUtil().setCaptureMuted(true), throwsStateError);
    expect(nativeMuted, isTrue);
    expect(SharedPreferencesUtil().capturePolicy, const CapturePolicy(revision: 5, muted: true));
    expect(store.data['flutter.capturePolicy'], '{"version":1,"revision":4,"muted":false}');
  });

  test('failed native mute still persists denial and surfaces the error', () async {
    SharedPreferencesUtil.capturePolicyBridgeForTesting = (method, arguments) async {
      if (method == 'getRevision') return 0;
      if (arguments['muted'] == true) throw StateError('channel unavailable');
      return true;
    };
    SharedPreferences.setMockInitialValues(<String, Object>{
      SharedPreferencesUtil.capturePolicyKey: '{"version":1,"revision":0,"muted":false}',
    });
    await SharedPreferencesUtil.init();
    await expectLater(SharedPreferencesUtil().setCaptureMuted(true), throwsStateError);
    final stored = await SharedPreferences.getInstance();
    expect(stored.getString(SharedPreferencesUtil.capturePolicyKey), '{"version":1,"revision":1,"muted":true}');
  });

  test('engine reconstruction retains a newer native mute revision', () async {
    final calls = <String>[];
    SharedPreferencesUtil.capturePolicyBridgeForTesting = (method, arguments) async {
      calls.add(method);
      return method == 'getRevision' ? 8 : true;
    };
    SharedPreferences.setMockInitialValues(<String, Object>{
      SharedPreferencesUtil.capturePolicyKey: '{"version":1,"revision":7,"muted":false}',
    });
    await SharedPreferencesUtil.init();
    expect(SharedPreferencesUtil().capturePolicy, const CapturePolicy(revision: 8, muted: true));
    expect(calls, ['getRevision']);
    expect(await SharedPreferencesUtil().setCaptureMuted(false), const CapturePolicy(revision: 9, muted: false));
  });

  test('failed unmute is surfaced and leaves effective state muted', () async {
    final store = _GatedPreferencesStore(<String, Object>{
      'flutter.capturePolicy': '{"version":1,"revision":4,"muted":true}',
    })
      ..failWrites = true;
    await _initWithStore(store);
    final prefs = SharedPreferencesUtil();

    await expectLater(prefs.setCaptureMuted(false), throwsStateError);
    expect(prefs.capturePolicy, const CapturePolicy(revision: 5, muted: true));
  });

  test('failed migration does not remove legacy flags', () async {
    final store = _GatedPreferencesStore(<String, Object>{
      'flutter.deviceMuted': false,
      'flutter.batchMuted': false,
    })
      ..failWrites = true;
    await _initWithStore(store);

    expect(SharedPreferencesUtil().capturePolicy, const CapturePolicy(revision: 0, muted: true));
    expect(store.data.containsKey('flutter.deviceMuted'), isTrue);
    expect(store.data.containsKey('flutter.batchMuted'), isTrue);
    expect(store.data.containsKey('flutter.capturePolicy'), isFalse);
  });
}

Future<void> _initWithStore(_GatedPreferencesStore store) async {
  SharedPreferences.resetStatic();
  SharedPreferencesStorePlatform.instance = store;
  await SharedPreferencesUtil.init();
}

class _GatedPreferencesStore extends SharedPreferencesStorePlatform {
  _GatedPreferencesStore(Map<String, Object> initial) : data = Map<String, Object>.from(initial);

  final Map<String, Object> data;
  final List<Completer<void>> _writeGates = <Completer<void>>[];
  int _writesStarted = 0;
  bool failWrites = false;

  Future<void> waitForWrite(int number) async {
    while (_writesStarted < number) {
      await Future<void>.delayed(Duration.zero);
    }
  }

  void releaseNextWrite() {
    expect(_writeGates, isNotEmpty);
    final gate = _writeGates.removeAt(0);
    if (!gate.isCompleted) gate.complete();
  }

  @override
  Future<Map<String, Object>> getAll() async => Map<String, Object>.from(data);

  @override
  Future<bool> setValue(String valueType, String key, Object value) async {
    if (key != 'flutter.capturePolicy') {
      data[key] = value;
      return true;
    }
    if (failWrites) return false;
    final gate = Completer<void>();
    _writesStarted++;
    _writeGates.add(gate);
    await gate.future;
    if (failWrites) return false;
    data[key] = value;
    return true;
  }

  @override
  Future<bool> remove(String key) async {
    data.remove(key);
    return true;
  }

  @override
  Future<bool> clear() async {
    data.clear();
    return true;
  }
}
