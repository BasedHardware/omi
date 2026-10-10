import 'dart:async';
import 'dart:convert';

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
  int? elapsedMs;
  int? androidElapsedMs;
  late List<({String name, Map<String, dynamic> properties})> events;
  late PhoneBatterySampleTelemetry sampler;
  var reads = 0;
  var build = '100';
  var identity = 'user-a';
  late ValueNotifier<int> identityChanges;
  Map<String, Object?>? snapshot;
  Future<Map<String, Object?>?> Function()? read;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
    consent = ValueNotifier(true);
    now = DateTime.utc(2026, 10, 8);
    elapsedMs = null;
    androidElapsedMs = null;
    events = [];
    reads = 0;
    snapshot = {'battery_level': 72, 'battery_charging': false, 'os_battery_saver': true};
    read = null;
    build = '100';
    identity = 'user-a';
    identityChanges = ValueNotifier(0);
    PackageInfo.setMockInitialValues(
        appName: 'Omi', packageName: 'com.omi.test', version: '1.0.558', buildNumber: build, buildSignature: '');
    sampler = PhoneBatterySampleTelemetry(
      preferences: () async => prefs,
      readBuild: () async => build,
      identity: () => identity,
      identityChanges: identityChanges,
      trackingConsent: consent,
      emit: (name, properties) => events.add((name: name, properties: properties)),
      now: () => now,
      monotonicMs: () => elapsedMs ?? now.millisecondsSinceEpoch,
      supported: true,
      readBattery: () async {
        reads++;
        final battery = await (read?.call() ?? Future.value(snapshot));
        return battery == null
            ? null
            : {
                ...battery,
                'elapsed_realtime_ms': androidElapsedMs ?? elapsedMs ?? now.millisecondsSinceEpoch,
              };
      },
    );
  });

  tearDown(() {
    sampler.dispose();
    consent.dispose();
    identityChanges.dispose();
  });

  Future<void> settleStorage(WidgetTester tester) async {
    for (var i = 0; i < 10; i++) {
      await tester.pump();
      await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    }
  }

  Future<void> foreground(WidgetTester tester) async {
    await tester.runAsync(sampler.start);
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await settleStorage(tester);
  }

  testWidgets('first v2 sample has typed nullable fields and an identity-fenced local baseline', (tester) async {
    await foreground(tester);
    expect(events.single.name, 'Phone Battery Sample');
    expect(events.single.properties, {
      'battery_level': 72,
      'battery_charging': false,
      'sampling_trigger': 'lifecycle_foreground',
      'os_battery_saver': true,
      'schema_version': 2,
      'battery_sample_at_ms': now.millisecondsSinceEpoch,
      'previous_battery_sample_at_ms': null,
      'previous_battery_level': null,
      'previous_battery_charging': null,
      'previous_battery_observation_build': null,
      'battery_interval_seconds': null,
      'battery_interval_validity': 'no_baseline',
      'battery_observation_build': '100',
      'foreground_seconds_in_interval': null,
      'app_lifecycle': 'resumed',
      'capture_source': 'unknown',
      'capture_mode': 'unknown',
      'seconds_since_build_first_run': 0.0,
      'thermal_state': null,
      'charging_observed_in_interval': null,
    });
    expect(prefs.getKeys(), {
      PhoneBatterySampleTelemetry.lastSampleKey,
      PhoneBatterySampleTelemetry.snapshotKey,
      PhoneBatterySampleTelemetry.buildFirstRunKey
    });
    final persisted = jsonDecode(prefs.getString(PhoneBatterySampleTelemetry.snapshotKey)!);
    expect(persisted['identity'], isNot('user-a'));
    expect(persisted['level'], 72);
    expect(prefs.getInt(PhoneBatterySampleTelemetry.lastSampleKey), now.millisecondsSinceEpoch);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('rapid lifecycle changes collapse; five-minute boundary and double elapsed survive restart', (
    tester,
  ) async {
    await foreground(tester);
    now = now.add(const Duration(minutes: 4, seconds: 59));
    sampler.didChangeAppLifecycleState(AppLifecycleState.hidden);
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await settleStorage(tester);
    expect(events, hasLength(1));
    expect(reads, 1);
    now = now.add(const Duration(seconds: 1, milliseconds: 250));
    sampler.dispose();
    sampler = PhoneBatterySampleTelemetry(
      preferences: () async => prefs,
      readBuild: () async => build,
      identity: () => identity,
      identityChanges: identityChanges,
      trackingConsent: consent,
      emit: (name, properties) => events.add((name: name, properties: properties)),
      now: () => now,
      monotonicMs: () => elapsedMs ?? now.millisecondsSinceEpoch,
      supported: true,
      readBattery: () async => snapshot,
    );
    await foreground(tester);
    expect(events, hasLength(2));
    expect(events.last.properties['seconds_since_previous_sample'], 300.25);
    expect(events.last.properties['seconds_since_previous_sample'], isA<double>());
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('hidden and paused map to one background sample and cancel timer', (tester) async {
    await foreground(tester);
    now = now.add(const Duration(minutes: 5));
    sampler.didChangeAppLifecycleState(AppLifecycleState.inactive);
    expect(sampler.hasForegroundTimer, false);
    sampler.didChangeAppLifecycleState(AppLifecycleState.hidden);
    await settleStorage(tester);
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await tester.pump(const Duration(minutes: 30));
    await settleStorage(tester);
    expect(events, hasLength(2));
    expect(events.last.properties['sampling_trigger'], 'lifecycle_background');
    expect(reads, 2);
    expect(sampler.hasForegroundTimer, false);
    now = now.add(const Duration(minutes: 30));
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await settleStorage(tester);
    expect(events.last.properties['sampling_trigger'], 'lifecycle_foreground');
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('timer samples only resumed foreground; detach and dispose cancel it', (tester) async {
    await foreground(tester);
    expect(sampler.hasForegroundTimer, true);
    now = now.add(const Duration(minutes: 15));
    await tester.pump(const Duration(minutes: 15));
    await settleStorage(tester);
    expect(events.last.properties['sampling_trigger'], 'timer_foreground');
    expect(events.last.properties['seconds_since_previous_sample'], 900.0);
    sampler.didChangeAppLifecycleState(AppLifecycleState.detached);
    await tester.pump(const Duration(minutes: 30));
    await settleStorage(tester);
    expect(events, hasLength(2));
    sampler.dispose();
    expect(sampler.hasForegroundTimer, false);
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('tracking disabled never starts a timer or reads battery', (tester) async {
    consent.value = false;
    await foreground(tester);
    await tester.pump(const Duration(hours: 1));
    await settleStorage(tester);
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await settleStorage(tester);
    expect(sampler.hasForegroundTimer, false);
    expect(reads, 0);
    expect(events, isEmpty);
    expect(prefs.getKeys().difference({PhoneBatterySampleTelemetry.buildFirstRunKey}), isEmpty);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('persisted opt-out wins over analytics startup default', (tester) async {
    await prefs.setBool('product_analytics_enabled', false);
    await foreground(tester);
    await tester.pump(const Duration(hours: 1));
    await settleStorage(tester);
    expect(sampler.hasForegroundTimer, false);
    expect(reads, 0);
    expect(events, isEmpty);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('opt-out immediately cancels timer; re-opt-in schedules foreground only', (tester) async {
    await foreground(tester);
    consent.value = false;
    expect(sampler.hasForegroundTimer, false);
    await tester.pump(const Duration(hours: 1));
    await settleStorage(tester);
    expect(reads, 1);
    consent.value = true;
    expect(sampler.hasForegroundTimer, true);
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    consent.value = false;
    consent.value = true;
    expect(sampler.hasForegroundTimer, false);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('failed battery read emits nothing and does not advance persisted sample', (tester) async {
    read = () async => throw PlatformException(code: 'battery_unavailable');
    await foreground(tester);
    expect(events, isEmpty);
    expect(prefs.getKeys().difference({PhoneBatterySampleTelemetry.buildFirstRunKey}), isEmpty);
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await settleStorage(tester);
    read = null;
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await settleStorage(tester);
    expect(events.single.properties.containsKey('seconds_since_previous_sample'), false);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('unknown or invalid level/charging never emits fake values', (tester) async {
    await tester.runAsync(sampler.start);
    for (final invalid in <Map<String, Object?>?>[
      null,
      {'battery_level': -1, 'battery_charging': false},
      {'battery_level': 101, 'battery_charging': false},
      {'battery_level': 50},
      {'battery_level': 50, 'battery_charging': 'unknown'},
    ]) {
      snapshot = invalid;
      sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
      await settleStorage(tester);
      sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
      await settleStorage(tester);
    }
    expect(events, isEmpty);
    expect(prefs.getKeys().difference({PhoneBatterySampleTelemetry.buildFirstRunKey}), isEmpty);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('charging and battery extremes are real values; unsupported saver is omitted', (tester) async {
    snapshot = {'battery_level': 0, 'battery_charging': true};
    await foreground(tester);
    expect(events.single.properties['battery_level'], 0);
    expect(events.single.properties['battery_charging'], true);
    expect(events.single.properties.containsKey('os_battery_saver'), false);
    now = now.add(const Duration(minutes: 5));
    snapshot = {'battery_level': 100, 'battery_charging': true, 'os_battery_saver': false};
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await settleStorage(tester);
    expect(events.last.properties['battery_level'], 100);
    expect(events.last.properties['os_battery_saver'], false);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

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
    await settleStorage(tester);
    expect(events, isEmpty);
    expect(prefs.getKeys().difference({PhoneBatterySampleTelemetry.buildFirstRunKey}), isEmpty);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('clock rollback skips reads and does not emit negative elapsed', (tester) async {
    await foreground(tester);
    now = now.subtract(const Duration(hours: 1));
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await settleStorage(tester);
    expect(events, hasLength(1));
    expect(reads, 1);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('manager opt-out synchronously notifies sampler without lifecycle transition', (tester) async {
    AnalyticsManager.resetForTesting();
    sampler.dispose();
    sampler = PhoneBatterySampleTelemetry(
      preferences: () async => prefs,
      readBuild: () async => build,
      identity: () => identity,
      identityChanges: identityChanges,
      emit: (name, properties) => events.add((name: name, properties: properties)),
      supported: true,
      readBattery: () async => snapshot,
    );
    await foreground(tester);
    expect(sampler.hasForegroundTimer, true);
    AnalyticsManager().optOutTracking();
    expect(sampler.hasForegroundTimer, false);
    await tester.pump(const Duration(hours: 1));
    await settleStorage(tester);
    expect(events, hasLength(1));
    sampler.dispose();
    AnalyticsManager.resetForTesting();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));
  testWidgets('foreground during preference loading still samples after startup', (tester) async {
    sampler.dispose();
    final pending = Completer<SharedPreferences>();
    sampler = PhoneBatterySampleTelemetry(
      preferences: () => pending.future,
      readBuild: () async => build,
      identity: () => identity,
      identityChanges: identityChanges,
      trackingConsent: consent,
      emit: (name, properties) => events.add((name: name, properties: properties)),
      supported: true,
      readBattery: () async => snapshot,
    );
    final startup = sampler.start();
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    expect(sampler.hasForegroundTimer, false);
    pending.complete(prefs);
    await settleStorage(tester);
    await startup;
    expect(events.single.name, 'Phone Battery Sample');
    expect(sampler.hasForegroundTimer, true);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  PhoneBatterySampleTelemetry restartedSampler() => PhoneBatterySampleTelemetry(
        preferences: () async => prefs,
        readBuild: () async => build,
        readBattery: () async => snapshot,
        trackingConsent: consent,
        identity: () => identity,
        identityChanges: identityChanges,
        now: () => now,
        monotonicMs: () => elapsedMs ?? now.millisecondsSinceEpoch,
        emit: (name, properties) => events.add((name: name, properties: properties)),
        supported: true,
      );

  testWidgets('previous v2 snapshot survives an upgrade with build_changed validity', (tester) async {
    await foreground(tester);
    final previousAt = now.millisecondsSinceEpoch;
    sampler.dispose();
    now = now.add(const Duration(minutes: 15));
    build = '101';
    snapshot = {'battery_level': 70, 'battery_charging': false};
    sampler = restartedSampler();
    await foreground(tester);
    final event = events.last.properties;
    expect(event['previous_battery_sample_at_ms'], previousAt);
    expect(event['previous_battery_level'], 72);
    expect(event['previous_battery_charging'], false);
    expect(event['previous_battery_observation_build'], '100');
    expect(event['battery_observation_build'], '101');
    expect(event['battery_interval_seconds'], 900.0);
    expect(event['battery_interval_validity'], 'build_changed');
    expect(event['seconds_since_build_first_run'], 0.0);
    expect(event['foreground_seconds_in_interval'], isNull); // process gap unknown
    now = now.add(const Duration(minutes: 15));
    await tester.pump(const Duration(minutes: 15));
    await settleStorage(tester);
    expect(events.last.properties['battery_interval_validity'], 'same_build');
    expect(events.last.properties['foreground_seconds_in_interval'], 900.0);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('build first-run age is durable and monotone per build; rollback cannot decrease it', (tester) async {
    await foreground(tester);
    now = now.add(const Duration(minutes: 15));
    await tester.pump(const Duration(minutes: 15));
    await settleStorage(tester);
    expect(events.last.properties['seconds_since_build_first_run'], 900.0);
    sampler.dispose();
    now = now.add(const Duration(minutes: 15));
    sampler = restartedSampler();
    await foreground(tester);
    expect(events.last.properties['seconds_since_build_first_run'], 1800.0);
    final marker = prefs.getString(PhoneBatterySampleTelemetry.buildFirstRunKey);
    sampler.dispose();
    now = now.subtract(const Duration(minutes: 5));
    sampler = restartedSampler();
    await foreground(tester);
    expect(prefs.getString(PhoneBatterySampleTelemetry.buildFirstRunKey), marker);
    sampler.dispose();
    build = '101';
    now = now.add(const Duration(minutes: 20));
    sampler = restartedSampler();
    await foreground(tester);
    expect(events.last.properties['seconds_since_build_first_run'], 0.0);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('identity switch clears baseline immediately and fences in-flight read', (tester) async {
    await foreground(tester);
    final pending = Completer<Map<String, Object?>?>();
    read = () => pending.future;
    now = now.add(const Duration(minutes: 15));
    await tester.pump(const Duration(minutes: 15));
    await settleStorage(tester);
    identity = 'user-b';
    identityChanges.value++;
    pending.complete(snapshot);
    await settleStorage(tester);
    expect(events, hasLength(1));
    expect(prefs.containsKey(PhoneBatterySampleTelemetry.snapshotKey), false);
    read = null;
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await settleStorage(tester);
    expect(events.last.properties['battery_interval_validity'], 'identity_changed');
    expect(events.last.properties['previous_battery_level'], isNull);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('restart under another identity never reuses local snapshot', (tester) async {
    await foreground(tester);
    sampler.dispose();
    identity = 'user-b';
    sampler = restartedSampler();
    await foreground(tester);
    expect(events.last.properties['battery_interval_validity'], 'identity_changed');
    expect(events.last.properties['previous_battery_sample_at_ms'], isNull);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('consent change clears baseline; re-opt-in never joins across opt-out', (tester) async {
    await foreground(tester);
    consent.value = false;
    await settleStorage(tester);
    expect(prefs.containsKey(PhoneBatterySampleTelemetry.snapshotKey), false);
    expect(prefs.containsKey(PhoneBatterySampleTelemetry.lastSampleKey), false);
    consent.value = true;
    now = now.add(const Duration(minutes: 15));
    await tester.pump(const Duration(minutes: 15));
    await settleStorage(tester);
    expect(events.last.properties['battery_interval_validity'], 'no_baseline');
    expect(events.last.properties['battery_interval_seconds'], isNull);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('foreground accumulation uses lifecycle spans; callback true applies to next interval only',
      (tester) async {
    await foreground(tester);
    now = now.add(const Duration(minutes: 2));
    sampler.recordPassiveCharging(true);
    now = now.add(const Duration(minutes: 2));
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused); // throttled, span still accounted
    await settleStorage(tester);
    now = now.add(const Duration(minutes: 6));
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await settleStorage(tester);
    expect(events.last.properties['battery_interval_seconds'], 600.0);
    expect(events.last.properties['foreground_seconds_in_interval'], 240.0);
    expect(events.last.properties['charging_observed_in_interval'], true);
    now = now.add(const Duration(minutes: 15));
    await tester.pump(const Duration(minutes: 15));
    await settleStorage(tester);
    expect(events.last.properties['charging_observed_in_interval'], isNull);
    expect(events.last.properties['thermal_state'], isNull);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('clock rollback inside a lifecycle span marks the next interval invalid', (tester) async {
    await foreground(tester);
    now = now.subtract(const Duration(minutes: 1));
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await settleStorage(tester);
    now = now.add(const Duration(minutes: 16));
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await settleStorage(tester);
    expect(events.last.properties['battery_interval_validity'], 'clock_invalid');
    expect(events.last.properties['foreground_seconds_in_interval'], isNull);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('rollback while backgrounded at +4min then +2min emits clock_invalid at +15min', (tester) async {
    elapsedMs = 0;
    await foreground(tester);
    final baseline = now;
    now = baseline.add(const Duration(minutes: 4));
    elapsedMs = 240000;
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await settleStorage(tester);
    now = baseline.add(const Duration(minutes: 2));
    elapsedMs = 300000;
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await settleStorage(tester);
    expect(events, hasLength(1)); // both transitions were throttled
    now = baseline.add(const Duration(minutes: 15));
    elapsedMs = 1080000;
    await tester.pump(const Duration(minutes: 15));
    await settleStorage(tester);
    expect(events.last.properties['battery_interval_seconds'], 900.0);
    expect(events.last.properties['battery_interval_validity'], 'clock_invalid');
    expect(events.last.properties['foreground_seconds_in_interval'], isNull);
    // A fresh, uncorrupted interval recovers.
    now = now.add(const Duration(minutes: 15));
    elapsedMs = 1980000;
    await tester.pump(const Duration(minutes: 15));
    await settleStorage(tester);
    expect(events.last.properties['battery_interval_validity'], 'same_build');
    sampler.dispose();
  }, variant: const TargetPlatformVariant({TargetPlatform.iOS, TargetPlatform.android}));

  testWidgets('forward wall-clock jump across a background transition emits clock_invalid', (tester) async {
    elapsedMs = 0;
    await foreground(tester);
    now = now.add(const Duration(minutes: 4));
    elapsedMs = 240000;
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await settleStorage(tester);
    now = now.add(const Duration(hours: 1));
    elapsedMs = 300000;
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await settleStorage(tester);
    expect(events.last.properties['battery_interval_validity'], 'clock_invalid');
    expect(events.last.properties['foreground_seconds_in_interval'], isNull);
    sampler.dispose();
  }, variant: const TargetPlatformVariant({TargetPlatform.iOS, TargetPlatform.android}));

  testWidgets('Android deep sleep after background at +4min remains same_build on resume at +15min', (tester) async {
    elapsedMs = 0;
    androidElapsedMs = 0;
    await foreground(tester);
    now = now.add(const Duration(minutes: 4));
    elapsedMs = 240000;
    androidElapsedMs = 240000;
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await settleStorage(tester);
    expect(events, hasLength(1)); // background snapshot is throttled
    now = now.add(const Duration(minutes: 11));
    elapsedMs = 300000; // CLOCK_MONOTONIC advanced only one minute: ten asleep
    androidElapsedMs = 900000; // elapsedRealtime includes the full sleep
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await settleStorage(tester);
    expect(events, hasLength(2));
    expect(events.last.properties['battery_interval_validity'], 'same_build');
    expect(events.last.properties['battery_interval_seconds'], 900.0);
    expect(events.last.properties['foreground_seconds_in_interval'], 240.0);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('normal foreground background cycle remains same_build with monotonic spans', (tester) async {
    elapsedMs = 0;
    await foreground(tester);
    now = now.add(const Duration(minutes: 4));
    elapsedMs = 240000;
    sampler.didChangeAppLifecycleState(AppLifecycleState.paused);
    await settleStorage(tester);
    now = now.add(const Duration(minutes: 11));
    elapsedMs = 900000;
    sampler.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await settleStorage(tester);
    expect(events.last.properties['battery_interval_validity'], 'same_build');
    expect(events.last.properties['battery_interval_seconds'], 900.0);
    expect(events.last.properties['foreground_seconds_in_interval'], 240.0);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('thermal snapshot passes known platform states; unavailable state stays null', (tester) async {
    snapshot = {'battery_level': 72, 'battery_charging': false, 'thermal_state': 'serious'};
    await foreground(tester);
    expect(events.last.properties['thermal_state'], 'serious');
    now = now.add(const Duration(minutes: 15));
    snapshot = {'battery_level': 72, 'battery_charging': false, 'thermal_state': 'severe'};
    await tester.pump(const Duration(minutes: 15));
    await settleStorage(tester);
    expect(events.last.properties['thermal_state'], 'severe');
    now = now.add(const Duration(minutes: 15));
    snapshot = {'battery_level': 72, 'battery_charging': false, 'thermal_state': 'unsupported'};
    await tester.pump(const Duration(minutes: 15));
    await settleStorage(tester);
    expect(events.last.properties['thermal_state'], isNull);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('unknown build and identity never fabricate a valid baseline', (tester) async {
    build = 'unknown';
    identity = '';
    await foreground(tester);
    expect(events.last.properties['battery_observation_build'], isNull);
    expect(events.last.properties['seconds_since_build_first_run'], isNull);
    now = now.add(const Duration(minutes: 15));
    await tester.pump(const Duration(minutes: 15));
    await settleStorage(tester);
    expect(events.last.properties['battery_interval_validity'], 'no_baseline');
    expect(events.last.properties['previous_battery_level'], isNull);
    expect(prefs.containsKey(PhoneBatterySampleTelemetry.snapshotKey), false);
    sampler.dispose();
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

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
    AnalyticsManager().bindIdentity('native-user');
    const channel = MethodChannel('com.omi/phone_battery');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, 'read');
      return {...?snapshot, 'elapsed_realtime_ms': 0};
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
        'schema_version': 2,
        'battery_observation_build': '456',
      });
    } finally {
      sampler.dispose();
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null);
      AnalyticsManager.resetForTesting();
    }
  });
}
