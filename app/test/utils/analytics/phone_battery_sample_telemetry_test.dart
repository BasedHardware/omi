import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/backend/preferences.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:omi/utils/analytics/phone_battery_sample_telemetry.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/recording_analytics.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late SharedPreferences prefs;
  late ValueNotifier<bool> consent;
  late DateTime now;
  late List<({String name, Map<String, dynamic> properties})> events;
  late PhoneBatterySampleTelemetry sampler;
  var reads = 0;
  Map<String, Object?>? snapshot;
  Future<Map<String, Object?>?> Function()? read;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
    consent = ValueNotifier(true);
    now = DateTime.utc(2026, 10, 8);
    events = [];
    reads = 0;
    snapshot = {'battery_level': 72, 'battery_charging': false, 'os_battery_saver': true};
    read = null;
    sampler = PhoneBatterySampleTelemetry(
      preferences: () async => prefs,
      trackingConsent: consent,
      emit: (name, properties) => events.add((name: name, properties: properties)),
      now: () => now,
      supported: true,
      readBattery: () {
        reads++;
        return read?.call() ?? Future.value(snapshot);
      },
    );
  });

  tearDown(() {
    sampler.dispose();
    consent.dispose();
  });

  Future<void> foreground(WidgetTester tester) async {
    await sampler.start();
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await tester.pump();
  }

  testWidgets('first phone sample has exact property types and timestamp-only persistence', (tester) async {
    await foreground(tester);
    expect(events.single.name, 'Phone Battery Sample');
    expect(events.single.properties, {
      'battery_level': 72,
      'battery_charging': false,
      'sampling_trigger': 'lifecycle_foreground',
      'os_battery_saver': true,
    });
    expect(prefs.getKeys(), {PhoneBatterySampleTelemetry.lastSampleKey});
    expect(prefs.getInt(PhoneBatterySampleTelemetry.lastSampleKey), now.millisecondsSinceEpoch);
    sampler.dispose();
  });

  testWidgets('rapid lifecycle changes collapse; five-minute boundary and double elapsed survive restart', (
    tester,
  ) async {
    await foreground(tester);
    now = now.add(const Duration(minutes: 4, seconds: 59));
    sampler.didChangeAppLifecycleState(AppLifecycleState.hidden);
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await tester.pump();
    expect(events, hasLength(1));
    expect(reads, 1);
    now = now.add(const Duration(seconds: 1, milliseconds: 250));
    sampler.dispose();
    sampler = PhoneBatterySampleTelemetry(
      preferences: () async => prefs,
      trackingConsent: consent,
      emit: (name, properties) => events.add((name: name, properties: properties)),
      now: () => now,
      supported: true,
      readBattery: () async => snapshot,
    );
    await foreground(tester);
    expect(events, hasLength(2));
    expect(events.last.properties['seconds_since_previous_sample'], 300.25);
    expect(events.last.properties['seconds_since_previous_sample'], isA<double>());
    sampler.dispose();
  });

  testWidgets('hidden and paused map to one background sample and cancel timer', (tester) async {
    await foreground(tester);
    now = now.add(const Duration(minutes: 5));
    sampler.didChangeAppLifecycleState(AppLifecycleState.inactive);
    expect(sampler.hasForegroundTimer, false);
    sampler.didChangeAppLifecycleState(AppLifecycleState.hidden);
    await tester.pump();
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await tester.pump(const Duration(minutes: 30));
    expect(events, hasLength(2));
    expect(events.last.properties['sampling_trigger'], 'lifecycle_background');
    expect(reads, 2);
    expect(sampler.hasForegroundTimer, false);
    now = now.add(const Duration(minutes: 30));
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await tester.pump();
    expect(events.last.properties['sampling_trigger'], 'lifecycle_foreground');
    sampler.dispose();
  });

  testWidgets('timer samples only resumed foreground; detach and dispose cancel it', (tester) async {
    await foreground(tester);
    expect(sampler.hasForegroundTimer, true);
    now = now.add(const Duration(minutes: 15));
    await tester.pump(const Duration(minutes: 15));
    expect(events.last.properties['sampling_trigger'], 'timer_foreground');
    expect(events.last.properties['seconds_since_previous_sample'], 900.0);
    sampler.didChangeAppLifecycleState(AppLifecycleState.detached);
    await tester.pump(const Duration(minutes: 30));
    expect(events, hasLength(2));
    sampler.dispose();
    expect(sampler.hasForegroundTimer, false);
  });

  testWidgets('tracking disabled never starts a timer or reads battery', (tester) async {
    consent.value = false;
    await foreground(tester);
    await tester.pump(const Duration(hours: 1));
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await tester.pump();
    expect(sampler.hasForegroundTimer, false);
    expect(reads, 0);
    expect(events, isEmpty);
    expect(prefs.getKeys(), isEmpty);
    sampler.dispose();
  });

  testWidgets('persisted opt-out wins over analytics startup default', (tester) async {
    await prefs.setBool('product_analytics_enabled', false);
    await foreground(tester);
    await tester.pump(const Duration(hours: 1));
    expect(sampler.hasForegroundTimer, false);
    expect(reads, 0);
    expect(events, isEmpty);
    sampler.dispose();
  });

  testWidgets('opt-out immediately cancels timer; re-opt-in schedules foreground only', (tester) async {
    await foreground(tester);
    consent.value = false;
    expect(sampler.hasForegroundTimer, false);
    await tester.pump(const Duration(hours: 1));
    expect(reads, 1);
    consent.value = true;
    expect(sampler.hasForegroundTimer, true);
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    consent.value = false;
    consent.value = true;
    expect(sampler.hasForegroundTimer, false);
    sampler.dispose();
  });

  testWidgets('failed battery read emits nothing and does not advance persisted sample', (tester) async {
    read = () async => throw PlatformException(code: 'battery_unavailable');
    await foreground(tester);
    expect(events, isEmpty);
    expect(prefs.getKeys(), isEmpty);
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await tester.pump();
    read = null;
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await tester.pump();
    expect(events.single.properties.containsKey('seconds_since_previous_sample'), false);
    sampler.dispose();
  });

  testWidgets('unknown or invalid level/charging never emits fake values', (tester) async {
    await sampler.start();
    for (final invalid in <Map<String, Object?>?>[
      null,
      {'battery_level': -1, 'battery_charging': false},
      {'battery_level': 101, 'battery_charging': false},
      {'battery_level': 50},
      {'battery_level': 50, 'battery_charging': 'unknown'},
    ]) {
      snapshot = invalid;
      sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
      await tester.pump();
      sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
      await tester.pump();
    }
    expect(events, isEmpty);
    expect(prefs.getKeys(), isEmpty);
    sampler.dispose();
  });

  testWidgets('charging and battery extremes are real values; unsupported saver is omitted', (tester) async {
    snapshot = {'battery_level': 0, 'battery_charging': true};
    await foreground(tester);
    expect(events.single.properties['battery_level'], 0);
    expect(events.single.properties['battery_charging'], true);
    expect(events.single.properties.containsKey('os_battery_saver'), false);
    now = now.add(const Duration(minutes: 5));
    snapshot = {'battery_level': 100, 'battery_charging': true, 'os_battery_saver': false};
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await tester.pump();
    expect(events.last.properties['battery_level'], 100);
    expect(events.last.properties['os_battery_saver'], false);
    sampler.dispose();
  });

  testWidgets('overlapping triggers and opt-out during a read cannot emit', (tester) async {
    final pending = Completer<Map<String, Object?>?>();
    read = () => pending.future;
    await foreground(tester);
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    expect(reads, 1);
    consent.value = false;
    consent.value = true;
    pending.complete(snapshot);
    await tester.pump();
    expect(events, isEmpty);
    expect(prefs.getKeys(), isEmpty);
    sampler.dispose();
  });

  testWidgets('clock rollback skips reads and does not emit negative elapsed', (tester) async {
    await foreground(tester);
    now = now.subtract(const Duration(hours: 1));
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await tester.pump();
    expect(events, hasLength(1));
    expect(reads, 1);
    sampler.dispose();
  });

  testWidgets('manager opt-out synchronously notifies sampler without lifecycle transition', (tester) async {
    AnalyticsManager.resetForTesting();
    sampler.dispose();
    sampler = PhoneBatterySampleTelemetry(
      preferences: () async => prefs,
      emit: (name, properties) => events.add((name: name, properties: properties)),
      supported: true,
      readBattery: () async => snapshot,
    );
    await foreground(tester);
    expect(sampler.hasForegroundTimer, true);
    AnalyticsManager().optOutTracking();
    expect(sampler.hasForegroundTimer, false);
    await tester.pump(const Duration(hours: 1));
    expect(events, hasLength(1));
    sampler.dispose();
    AnalyticsManager.resetForTesting();
  });
  testWidgets('foreground during preference loading still samples after startup', (tester) async {
    sampler.dispose();
    final pending = Completer<SharedPreferences>();
    sampler = PhoneBatterySampleTelemetry(
      preferences: () => pending.future,
      trackingConsent: consent,
      emit: (name, properties) => events.add((name: name, properties: properties)),
      supported: true,
      readBattery: () async => snapshot,
    );
    final startup = sampler.start();
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    expect(sampler.hasForegroundTimer, false);
    pending.complete(prefs);
    await startup;
    await tester.pump();
    expect(events.single.name, 'Phone Battery Sample');
    expect(sampler.hasForegroundTimer, true);
    sampler.dispose();
  });

  test('default native channel and AnalyticsManager preserve build context', () async {
    AnalyticsManager.resetForTesting();
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '1.2.3',
      buildNumber: '456',
      buildSignature: '',
    );
    await SharedPreferencesUtil.init();
    final recording = RecordingAnalytics();
    AnalyticsManager.configure(recording.adapter);
    await AnalyticsManager.init();
    const channel = MethodChannel('com.omi/phone_battery');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, 'read');
      return snapshot;
    });
    sampler.dispose();
    sampler = PhoneBatterySampleTelemetry(preferences: () async => prefs, supported: true);
    try {
      await sampler.start();
      sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
      // Let the platform reply and timestamp write complete before flushing.
      await Future<void>.delayed(Duration.zero);
      await AnalyticsManager.flushPending(force: true);
      recording.expectSingle('Phone Battery Sample', {
        'battery_level': 72,
        'battery_charging': false,
        'sampling_trigger': 'lifecycle_foreground',
        'os_battery_saver': true,
        'app_version': '1.2.3',
        'app_build': '456',
      });
    } finally {
      sampler.dispose();
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null);
      AnalyticsManager.resetForTesting();
    }
  });
}
