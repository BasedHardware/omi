import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/env/physical_qualification.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/debugging/crashlytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';

class _StartupDocuments extends PathProviderPlatform {
  _StartupDocuments(this.path);
  final String path;

  @override
  Future<String> getApplicationDocumentsPath() async => path;
}

class _QualificationAnalytics extends AnalyticsAdapter {
  final calls = <Symbol>[];

  @override
  bool get isInitialized => true;

  @override
  Future<void> init() async => calls.add(#init);

  @override
  void registerSuperProperties(Map<String, Object> properties) => calls.add(#registerSuperProperties);

  @override
  dynamic noSuchMethod(Invocation invocation) {
    calls.add(invocation.memberName);
    return null;
  }
}

void main() {
  if (!PhysicalQualification.enabled) {
    test('ordinary runtime diagnostics need no platform plugins', () async {
      await PhysicalQualification.runtimeEvent('ignored', error: StateError('private'), stack: StackTrace.current);
    });
    test('ordinary startup returns original future without platform or diagnostic work', () {
      final original = Future<int>.value(42);
      var calls = 0;
      final observed = PhysicalQualification.startupStage('ordinary', () {
        calls++;
        return original;
      });
      expect(identical(observed, original), isTrue);
      expect(calls, 1);
    });
  } else {
    test('runtime journal serializes markers and retains only exception type and source locations', () async {
      final temporary = await Directory.systemTemp.createTemp('omi-runtime-stage-');
      final previous = PathProviderPlatform.instance;
      PathProviderPlatform.instance = _StartupDocuments(temporary.path);
      try {
        final writes = [
          PhysicalQualification.runtimeEvent('run_app_scheduled'),
          PhysicalQualification.runtimeEvent('flutter_error',
              error: StateError('sensitive-token'),
              stack: StackTrace.fromString('sensitive-token\n'
                  '#0      MyApp.build (package:omi/main.dart:321:7)\n'
                  '#1      run (dart:async/zone.dart:11:2)\n'
                  '#2      private (https://example.test/sensitive-token:1:1)\n')),
          PhysicalQualification.runtimeEvent('first_frame_callback'),
        ];
        await Future.wait(writes);
        final raw = await File('${temporary.path}/physical_capture_runtime.jsonl').readAsString();
        expect(raw, isNot(contains('sensitive-token')));
        final records = raw.trim().split('\n').map((line) => jsonDecode(line) as Map<String, dynamic>).toList();
        expect(records.map((record) => record['kind']), ['run_app_scheduled', 'flutter_error', 'first_frame_callback']);
        expect(records[1]['error_type'], 'StateError');
        expect(records[1]['frames'], [
          {'source': 'package:omi/main.dart', 'line': 321, 'column': 7},
          {'source': 'dart:async/zone.dart', 'line': 11, 'column': 2},
        ]);
        expect(records[1].keys.toSet(), {'kind', 'at_ms', 'error_type', 'frames'});
      } finally {
        PathProviderPlatform.instance = previous;
        await temporary.delete(recursive: true);
      }
    });

    test('startup records a pending await and failure type without sensitive error text', () async {
      final temporary = await Directory.systemTemp.createTemp('omi-startup-stage-');
      final previous = PathProviderPlatform.instance;
      PathProviderPlatform.instance = _StartupDocuments(temporary.path);
      try {
        final pending = Completer<int>();
        final entered = Completer<void>();
        final result = PhysicalQualification.startupStage('fixture_signin', () {
          entered.complete();
          return pending.future;
        });
        await entered.future;
        final receipt = File('${temporary.path}/physical_capture_startup.json');
        final before = jsonDecode(await receipt.readAsString()) as Map<String, dynamic>;
        expect(before.keys.toSet(), {'stage', 'state', 'error_type', 'at_ms'});
        expect(before['stage'], 'fixture_signin');
        expect(before['state'], 'begin');
        expect(before['error_type'], isNull);
        expect(before['at_ms'], isA<int>());
        final failure = StateError('sensitive-token-must-never-appear');
        final assertion = expectLater(result, throwsA(same(failure)));
        pending.completeError(failure);
        await assertion;
        final failedText = await receipt.readAsString();
        final failed = jsonDecode(failedText);
        expect(failed['state'], 'failed');
        expect(failed['error_type'], 'StateError');
        expect(failedText, isNot(contains('sensitive-token')));
        expect(await PhysicalQualification.startupStage('service_manager_start', () async => 7), 7);
        expect(jsonDecode(await receipt.readAsString())['state'], 'completed');
        expect(await File('${receipt.path}.tmp').exists(), isFalse);
      } finally {
        PathProviderPlatform.instance = previous;
        await temporary.delete(recursive: true);
      }
    });
  }

  group('wearable selection', () {
    const fixture = 'omi-physical-fixture-wearable-test';
    const scan = 'boot-1-scan-1';
    const peripheral = 'AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE';
    final selected = {
      'command': 'select_wearable',
      'fixture_uid': fixture,
      'run_id': 'server-run-1',
      'scan_id': scan,
      'peripheral_id': peripheral,
    };
    String? choose(Map<String, dynamic> control, {List<String> ids = const [peripheral]}) =>
        PhysicalQualification.selectedWearable(
          control: control,
          scanId: scan,
          fixtureUid: fixture,
          candidateIds: ids,
        );

    test('wait never selects and matching host approval selects the sole candidate', () {
      expect(choose({'command': 'wait'}), isNull);
      expect(choose(selected), peripheral);
    });

    test('stale scan, wrong fixture, wrong device, missing run and wrong command refuse', () {
      for (final replacement in [
        {'scan_id': 'older-scan'},
        {'fixture_uid': 'another-fixture'},
        {'peripheral_id': 'another-device'},
        {'run_id': ''},
        {'command': 'upload'},
      ]) {
        expect(() => choose({...selected, ...replacement}), throwsStateError, reason: replacement.keys.single);
      }
      expect(() => choose({...selected}..remove('run_id')), throwsStateError);
    });

    test('zero, ambiguous and empty candidate inventories fail before waiting or connection', () {
      for (final ids in <List<String>>[
        [],
        [''],
        [peripheral, 'another-device'],
        [peripheral, peripheral]
      ]) {
        expect(() => choose({'command': 'wait'}, ids: ids), throwsStateError);
        expect(() => choose(selected, ids: ids), throwsStateError);
      }
    });
  });

  if (PhysicalQualification.enabled) {
    test('opt-in excludes analytics initialization, identity and experiment refresh even with an adapter', () async {
      AnalyticsManager.resetForTesting();
      final adapter = _QualificationAnalytics();
      AnalyticsManager.configure(adapter);
      try {
        final analytics = AnalyticsManager();
        analytics.bindIdentity('omi-physical-fixture-test');
        await AnalyticsManager.init();
        await analytics.refreshExperiments();
        analytics.recordProductError(ProductErrorKind.uncaughtDart);
        analytics.recordTelemetryHealth();
        await AnalyticsManager.flushPending(force: true);
        expect(adapter.calls, isEmpty);
        expect(AnalyticsManager.queuedEventCountForTesting, 0);
      } finally {
        AnalyticsManager.resetForTesting();
      }
    });

    test('opt-in disables external SDK capabilities before initialization', () {
      expect(PlatformService.isAnalyticsSupported, isFalse);
      expect(PlatformService.isIntercomSupported, isFalse);
      expect(PlatformService.isCrashlyticsSupported, isFalse);
      expect(PlatformManager.instance.isFCMSupported, isFalse);
    });

    test('opt-in crash reporting needs no Firebase or native plugin', () async {
      await CrashlyticsManager.init();
      final reporter = CrashlyticsManager.instance;
      reporter.setEnabled(true);
      reporter.identifyUser('fixture@local.test', 'Fixture', 'omi-physical-fixture-test');
      reporter.logInfo('fixture');
      reporter.logError('fixture');
      reporter.logWarn('fixture');
      reporter.logDebug('fixture');
      reporter.logVerbose('fixture');
      await reporter.reportCrash(StateError('fixture'), StackTrace.current, userAttributes: {'fixture': 'true'});
    });
  }
  test('qualification accepts only literal private destinations', () {
    for (final host in ['127.0.0.1', '::1', '10.0.0.1', '172.16.1.2', '192.168.1.2', '100.64.0.1', '100.127.255.254']) {
      expect(PhysicalQualification.isPrivateLiteral(host), isTrue, reason: host);
    }
    for (final host in [
      'example.com',
      'localhost',
      '0.0.0.0',
      '169.254.1.1',
      '172.15.0.1',
      '172.32.0.1',
      '100.63.0.1',
      '100.128.0.1',
      '8.8.8.8'
    ]) {
      expect(PhysicalQualification.isPrivateLiteral(host), isFalse, reason: host);
    }
  });

  test('exact session port and proxy denial survive an allowed redirect source', () {
    final policy = PhysicalQualificationHttpOverrides({'127.0.0.1:18765'});
    expect(policy.allowsConnection(Uri.parse('http://127.0.0.1:18765/v1/health'), null), isTrue);
    for (final target in ['http://127.0.0.1:19099/', 'http://localhost:18765/', 'https://example.com/']) {
      expect(policy.allowsConnection(Uri.parse(target), null), isFalse);
    }
    expect(policy.allowsConnection(Uri.parse('http://127.0.0.1:18765/'), '127.0.0.1'), isFalse);
  });

  test('unapproved real HttpClient request fails before socket creation', () async {
    final policy = PhysicalQualificationHttpOverrides({});
    await HttpOverrides.runWithHttpOverrides(() async {
      final client = HttpClient();
      try {
        await expectLater(client.getUrl(Uri.parse('http://192.0.2.1:43210/')), throwsA(isA<SocketException>()));
      } finally {
        client.close(force: true);
      }
    }, policy);
  });
}
