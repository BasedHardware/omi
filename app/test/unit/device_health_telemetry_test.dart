import 'dart:convert';
import 'dart:async';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/adapters/posthog_adapter.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:omi/utils/analytics/device_health_telemetry.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    await DeviceHealthTelemetry.policySettled;
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  tearDown(() async {
    await DeviceHealthTelemetry.policySettled;
    AnalyticsManager.resetForTesting();
    debugDefaultTargetPlatformOverride = null;
  });

  test('daily rollup clips connected duration and counts only that day', () {
    final day = DateTime(2026, 9, 27);
    final start = day.millisecondsSinceEpoch;
    final result = DeviceHealthTelemetry.rollup({
      'disconnect_history_v2': [
        {
          'timestamp': start + 60 * 60 * 1000,
          'eventType': 'disconnect',
          'connectionDurationMs': 2 * 60 * 60 * 1000,
          'reason': 'connection_timeout',
          'timeToReconnectMs': 7000,
          'lastRssi': -80,
          'lostAudioSeconds': 5.5,
          'audioPacketsReceived': 8,
          'audioPacketsExpected': 10,
        }
      ],
      'battery_history_v2': [
        {'ts': start, 'level': 80, 'charging': false},
        {'ts': start + 60 * 60 * 1000, 'level': 78, 'charging': false},
        {'ts': start + 2 * 60 * 60 * 1000, 'level': 79, 'charging': true},
      ],
      'firmware_diagnostics': [
        {
          'ts': start + 1000,
          'reset_cause_names': ['RESET_WATCHDOG']
        },
      ],
    }, day);
    expect(result['connected_time_fraction'], closeTo(1 / 24, 0.00001));
    expect(result['disconnects_by_reason'], {'connection_timeout': 1});
    expect(result['reconnect_latency_buckets'], {'<30': 1});
    expect(result['rssi_at_disconnect_buckets'], {'<-75': 1});
    expect(result['lost_audio_seconds'], 5.5);
    expect(result['audio_packet_loss_ratio'], isNull); // Cross-midnight legacy totals are unknown.
    expect(result['drain_percent_per_hour'], 2);
    expect(result['charge_events'], 1);
    expect(result['device_resets_by_reason'], {'RESET_WATCHDOG': 1});
    expect(result['cliff_count'], 0);
    expect(result['max_step_drop'], 0);
    expect(result['max_step_drop_seconds'], 0);
    expect(result.containsKey('charge_pin_edges_max'), isFalse);
    expect(result.containsKey('soc_frozen_samples'), isFalse);
  });

  test('omitted charging still counts drain and a five second battery cliff', () {
    final day = DateTime(2026, 9, 27);
    final start = day.millisecondsSinceEpoch;
    final result = DeviceHealthTelemetry.rollup({
      'battery_history_v2': [
        {'ts': start, 'level': 100},
        {'ts': start + 5000, 'level': 45},
      ],
    }, day);
    expect(result['drain_percent_per_hour'], closeTo(55 * 3600 / 5, 0.00001));
    expect(result['charge_events'], 0);
    expect(result['cliff_count'], 1);
    expect(result['max_step_drop'], 55);
    expect(result['max_step_drop_seconds'], 5);
  });

  test('a fourteen hour drop is neither a cliff nor a drain window', () {
    final day = DateTime(2026, 9, 27);
    final start = day.millisecondsSinceEpoch;
    final result = DeviceHealthTelemetry.rollup({
      'battery_history_v2': [
        {'ts': start, 'level': 100},
        {'ts': start + 14 * 60 * 60 * 1000, 'level': 48},
      ],
    }, day);
    expect(result['cliff_count'], 0);
    expect(result['max_step_drop'], 0);
    expect(result['max_step_drop_seconds'], 0);
    expect(result['drain_percent_per_hour'], 0);
  });

  test('unknown charging on either side includes JSON null without a charge event', () {
    final day = DateTime(2026, 9, 27);
    final start = day.millisecondsSinceEpoch;
    for (final states in [
      [null, false],
      [false, null],
      [null, null],
    ]) {
      final result = DeviceHealthTelemetry.rollup({
        'battery_history_v2': [
          {'ts': start, 'level': 80, 'charging': states[0]},
          {'ts': start + 3600000, 'level': 78, 'charging': states[1]},
        ],
      }, day);
      expect(result['drain_percent_per_hour'], 2);
      expect(result['charge_events'], states[0] == true ? 1 : 0);
    }
  });

  test('an explicitly charging endpoint excludes the interval even when the other side is unknown', () {
    final day = DateTime(2026, 9, 27);
    final start = day.millisecondsSinceEpoch;
    for (final states in [
      [true, null],
      [null, true],
      [true, false],
    ]) {
      final result = DeviceHealthTelemetry.rollup({
        'battery_history_v2': [
          {'ts': start, 'level': 80, 'charging': states[0]},
          {'ts': start + 3600000, 'level': 78, 'charging': states[1]},
        ],
      }, day);
      expect(result['drain_percent_per_hour'], 0);
    }
  });

  test('a drain window crossing midnight is counted once, by the later day', () {
    final day = DateTime(2026, 9, 28);
    final start = day.millisecondsSinceEpoch;
    final battery = [
      {'ts': start - 5 * 60 * 1000, 'level': 80}, // 23:55 the previous day.
      {'ts': start + 5 * 60 * 1000, 'level': 78}, // 00:05 this day.
    ];
    final laterDay = DeviceHealthTelemetry.rollup({'battery_history_v2': battery}, day);
    expect(laterDay['drain_percent_per_hour'], closeTo(12, 0.00001));
    final earlierDay = DeviceHealthTelemetry.rollup({'battery_history_v2': battery}, DateTime(2026, 9, 27));
    expect(earlierDay['drain_percent_per_hour'], 0);
  });

  test('cliffs require consecutive in-day points and retain the largest pair gap', () {
    final day = DateTime(2026, 9, 27);
    final start = day.millisecondsSinceEpoch;
    final result = DeviceHealthTelemetry.rollup({
      'battery_history_v2': [
        {'ts': start - 1, 'level': 100},
        {'ts': start, 'level': 40}, // The previous day cannot form a pair.
        {'ts': start + 1000, 'level': 100},
        {'ts': start + 601000, 'level': 70, 'charging': true}, // Ten minutes, exactly 30.
        {'ts': start + 602000, 'level': 100},
        {'ts': start + 607000, 'level': 45},
        {'ts': start + 607000, 'level': 0}, // Zero elapsed time.
        {'ts': start + 608000, 'level': 100},
        {'ts': start + 1208001, 'level': 40}, // More than ten minutes.
        {'ts': start + 86400000, 'level': 0}, // Outside the day.
      ],
    }, day);
    expect(result['cliff_count'], 2);
    expect(result['max_step_drop'], 55);
    expect(result['max_step_drop_seconds'], 5);
  });

  test('optional firmware tail aggregates samples before boot deduplication', () {
    final day = DateTime(2026, 9, 27);
    final start = day.millisecondsSinceEpoch;
    final result = DeviceHealthTelemetry.rollup({
      'firmware_diagnostics': [
        {'ts': start - 1, 'charge_pin_edges': 100, 'soc_frozen': true, 'last_off_charger_mv': 999},
        {'ts': start, 'charge_pin_edges': 4, 'soc_frozen': true, 'last_off_charger_mv': 4000},
        {'ts': start + 1000, 'charge_pin_edges': 7, 'soc_frozen': true, 'last_off_charger_mv': 3700},
        {'ts': start + 2000, 'charge_pin_edges': 2, 'soc_frozen': false, 'last_off_charger_mv': null},
        {'ts': start + 3000, 'charge_pin_edges': null, 'soc_frozen': null},
      ],
    }, day);
    expect(result['charge_pin_edges_max'], 7);
    expect(result['soc_frozen_samples'], 2);
    expect(result['last_off_charger_mv_min'], 3700);
    expect(result['last_off_charger_mv_max'], 4000);
  });
  // TODO(merge-order): remove the skip once #21152's delivery fix is merged.
  test('never recovered outage emits loss after restart, capped per device day', () async {
    final delivered = await setupDelivery();
    final day = DateTime(2026, 10, 9);
    final start = day.millisecondsSinceEpoch;
    const id = 'unresolved-restart';
    // Seed only the durable record: no in-memory disconnect/recovery state.
    SharedPreferences.setMockInitialValues({
      DeviceHealthTelemetry.outageKey(id):
          jsonEncode({'identity_epoch': AnalyticsManager.identityEpoch, 'open_since': start - 86400000}),
      'device_health_day_$id': '2026-10-08',
    });
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 10),
        loadDiagnostics: (_) async => '{}',
        emissionContext: {'app_build': 'new+2'},
        emit: (name, properties) => AnalyticsManager().track(name, properties: properties));
    await drainDelivery();
    events.addAll(delivered);
    expect(events, hasLength(1));
    expect(events.single['lost_audio_seconds'], 86400);
    expect(events.single['unresolved_outage_seconds'], 86400);
    expect(events.single['unresolved_outage_open'], isTrue);
    expect(events.single['schema_version'], 2);
  }, tags: ['depends_on_21152']);

  test('first recovered packet splits durable outage at midnight after process death', () async {
    final start = DateTime(2026, 10, 9, 23, 59);
    const id = 'recovered-restart';
    SharedPreferences.setMockInitialValues({
      DeviceHealthTelemetry.outageKey(id):
          jsonEncode({'identity_epoch': AnalyticsManager.identityEpoch, 'open_since': start.millisecondsSinceEpoch}),
    });
    await DeviceHealthTelemetry.recordRecovery(id, at: DateTime(2026, 10, 10, 0, 1));
    final prefs = await SharedPreferences.getInstance();
    final record = jsonDecode(prefs.getString(DeviceHealthTelemetry.outageKey(id))!) as Map;
    expect(record.containsKey('open_since'), isFalse);
    final result =
        DeviceHealthTelemetry.rollup({'outage_resolved_days': record['resolved_days']}, DateTime(2026, 10, 10));
    expect(result['lost_audio_seconds'], 60);
    expect(
        DeviceHealthTelemetry.rollup(
            {'outage_resolved_days': record['resolved_days']}, DateTime(2026, 10, 9))['lost_audio_seconds'],
        60);
    expect(result['unresolved_outage_open'], isFalse);
    expect(result['unresolved_outage_seconds'], isNull);
  });

  // TODO(merge-order): remove the skip once #21152's delivery fix is merged.
  test('backfilled emission uses observation build and firmware, skips missing days', () async {
    final delivered = await setupDelivery();
    const id = 'provenance';
    final oldDay = DateTime(2026, 10, 8);
    final newDay = DateTime(2026, 10, 10);
    SharedPreferences.setMockInitialValues({'device_health_day_$id': '2026-10-07'});
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id, firmwareRevision: 'current'),
        now: DateTime(2026, 10, 11),
        emissionContext: {'app_build': 'current+3'},
        loadDiagnostics: (_) async => jsonEncode({
              'battery_history_v2': [
                {'ts': oldDay.millisecondsSinceEpoch, 'level': 80, 'app_build': 'old+1', 'firmware': 'fw1'},
                {'ts': newDay.millisecondsSinceEpoch, 'level': 70, 'app_build': 'new+2', 'firmware': null},
              ]
            }),
        emit: (name, properties) => AnalyticsManager().track(name, properties: properties));
    await drainDelivery();
    events.addAll(delivered);
    expect(events.map((e) => e['day']), ['2026-10-08', '2026-10-10']);
    expect(events.first['schema_version'], 2);
    expect(events.first['app_version'], 'old+1');
    expect(events.last['app_version'], 'new+2');
    expect(events.first['day_app_build'], ['old+1']);
    expect(events.first['day_firmware'], ['fw1']);
    expect(events.first['firmware'], 'fw1');
    expect(events.last['day_app_build'], ['new+2']);
    expect(events.last['day_firmware'], isNull);
    expect(events.first['os_version'], isNull);
  }, tags: ['depends_on_21152']);

  test('active packet counts use day observations across midnight', () {
    final day = DateTime(2026, 10, 10);
    final start = day.millisecondsSinceEpoch;
    final result = DeviceHealthTelemetry.rollup({
      'connected_at': start - 3600000,
      'observed_at': start + 3600000,
      'audio_packets_received': 1000,
      'audio_packets_expected': 2000,
      'audio_packet_days': [
        {'ts': start - 86400000, 'received': 90, 'expected': 100},
        {'ts': start, 'received': 8, 'expected': 10},
        {'ts': start + 86400000, 'received': 0, 'expected': 100},
      ],
    }, day);
    expect(result['audio_packet_loss_ratio'], 0.2);
    expect(result['connected_time_fraction'], closeTo(1 / 24, 0.00001));
  });

  test('duplicate starts preserve earliest outage and catch-up stays within seven days', () async {
    const id = 'bounded';
    await DeviceHealthTelemetry.recordOutage(id, at: DateTime(2026, 9, 1));
    await DeviceHealthTelemetry.recordOutage(id, at: DateTime(2026, 10, 10));
    SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setString('device_health_day_$id', '2026-09-01');
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 11),
        emissionContext: {},
        loadDiagnostics: (_) async => '{}',
        emit: (_, props) => events.add(props));
    expect(events, hasLength(7));
    expect(events.first['day'], '2026-10-04');
    expect(events.every((e) => e['lost_audio_seconds'] == 86400), isTrue);
  });
  test('native recoveries are imported once while a newer outage stays open', () async {
    const id = 'native-catch-up';
    final start = DateTime(2026, 10, 9, 12).millisecondsSinceEpoch;
    final nextStart = start + 3600000;
    await DeviceHealthTelemetry.recordOutage(id, at: DateTime.fromMillisecondsSinceEpoch(start));
    final diagnostics = jsonEncode({
      'audio_outage_started_at': nextStart,
      'disconnect_history_v2': [
        {'timestamp': start, 'lostAudioResolvedAt': start + 60000}
      ],
    });
    for (var attempt = 0; attempt < 2; attempt++) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove('device_health_day_$id');
      final events = <Map<String, dynamic>>[];
      await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
          now: DateTime(2026, 10, 10),
          emissionContext: {},
          loadDiagnostics: (_) async => diagnostics,
          emit: (_, props) => events.add(props));
      expect(events.single['lost_audio_seconds'], 11 * 3600 + 60);
      expect(events.single['unresolved_outage_seconds'], 11 * 3600);
      expect(events.single['unresolved_outage_open'], isTrue);
    }
  });
  test('open emission then recovery emits exactly 3600 plus 3600 across midnight', () async {
    const id = 'exact-midnight';
    await DeviceHealthTelemetry.recordOutage(id, at: DateTime(2026, 10, 9, 23));
    final events = <Map<String, dynamic>>[];
    Future<void> emit(DateTime now) => DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: now, emissionContext: {}, loadDiagnostics: (_) async => '{}', emit: (_, props) => events.add(props));
    await emit(DateTime(2026, 10, 10, 0, 30));
    await DeviceHealthTelemetry.recordRecovery(id, at: DateTime(2026, 10, 10, 1));
    await emit(DateTime(2026, 10, 11));
    expect(events.map((e) => e['lost_audio_seconds']), [3600, 3600]);
    expect(events.last['unresolved_outage_open'], isFalse);
  });

  test('three day recovery before catch-up preserves slices and per-day cap', () async {
    const id = 'three-days';
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('device_health_day_$id', '2026-10-08');
    await DeviceHealthTelemetry.recordOutage(id, at: DateTime(2026, 10, 9, 23));
    await DeviceHealthTelemetry.recordRecovery(id, at: DateTime(2026, 10, 12, 1));
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 13),
        emissionContext: {},
        loadDiagnostics: (_) async => '{}',
        emit: (_, props) => events.add(props));
    expect(events.map((e) => e['lost_audio_seconds']), [3600, 86400, 86400, 3600]);
    expect(events.fold<num>(0, (total, e) => total + (e['lost_audio_seconds'] as num)), 180000);
    expect(events.every((e) => (e['lost_audio_seconds'] as num) <= 86400), isTrue);
  });

  test('opt-out gates both writers and invalidates pending one-way write', () async {
    const id = 'consent';
    final pending = DeviceHealthTelemetry.recordOutage(id, at: DateTime(2026, 10, 9));
    AnalyticsManager().optOutTracking();
    await pending;
    await DeviceHealthTelemetry.policySettled;
    await DeviceHealthTelemetry.recordOutage(id);
    await DeviceHealthTelemetry.recordRecovery(id);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString(DeviceHealthTelemetry.outageKey(id)), isNull);
  });

  test('account switch discards prior records and fences diagnostics in flight', () async {
    const id = 'account';
    AnalyticsManager().bindIdentity('old-account');
    await DeviceHealthTelemetry.policySettled;
    await DeviceHealthTelemetry.recordOutage(id, at: DateTime(2026, 10, 9));
    final prefs = await SharedPreferences.getInstance();
    final old = prefs.getString(DeviceHealthTelemetry.outageKey(id))!;
    AnalyticsManager().bindIdentity('new-account');
    await DeviceHealthTelemetry.policySettled;
    expect(prefs.getString(DeviceHealthTelemetry.outageKey(id)), isNull);
    await prefs.setString(DeviceHealthTelemetry.outageKey(id), old);
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 10),
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'identity_epoch': AnalyticsManager.identityEpoch,
              'battery_history_v2': [
                {
                  'identity_epoch': AnalyticsManager.identityEpoch - 1,
                  'ts': DateTime(2026, 10, 9).millisecondsSinceEpoch,
                  'level': 80
                }
              ],
              'disconnect_history_v2': [
                {
                  'identity_epoch': AnalyticsManager.identityEpoch - 1,
                  'timestamp': DateTime(2026, 10, 9).millisecondsSinceEpoch,
                  'lostAudioResolvedAt': DateTime(2026, 10, 9, 1).millisecondsSinceEpoch
                }
              ]
            }),
        emit: (_, props) => events.add(props));
    expect(events, isEmpty);
    await DeviceHealthTelemetry.recordOutage(id, at: DateTime(2026, 10, 10));
    final record = jsonDecode(prefs.getString(DeviceHealthTelemetry.outageKey(id))!) as Map;
    expect(record['identity_epoch'], AnalyticsManager.identityEpoch);
    expect(record['open_since'], DateTime(2026, 10, 10).millisecondsSinceEpoch);
  });

  test('native session marker reconstructs unknown open outage until reconnect recovery', () async {
    const id = 'native-session-kill';
    final start = DateTime(2026, 10, 9, 23);
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 10),
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'identity_epoch': AnalyticsManager.identityEpoch,
              'audio_outage_started_at': start.millisecondsSinceEpoch,
            }),
        emit: (_, props) => events.add(props));
    expect(events.single['unresolved_outage_open'], isTrue);
    expect(events.single['lost_audio_seconds'], 3600);
    await DeviceHealthTelemetry.recordRecovery(id, at: DateTime(2026, 10, 10, 1));
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 11),
        emissionContext: {},
        loadDiagnostics: (_) async => '{}',
        emit: (_, props) => events.add(props));
    expect(events.last['unresolved_outage_open'], isFalse);
    expect(events.last['lost_audio_seconds'], 3600);
  });

  test('identity change fences an in-flight native diagnostics import', () async {
    AnalyticsManager().bindIdentity('before-load');
    await DeviceHealthTelemetry.policySettled;
    final raw = Completer<String>();
    final entered = Completer<void>();
    final events = <Map<String, dynamic>>[];
    final emission = DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: 'late-import'),
        now: DateTime(2026, 10, 10),
        emissionContext: {},
        loadDiagnostics: (_) {
          entered.complete();
          return raw.future;
        },
        emit: (_, props) => events.add(props));
    await entered.future;
    AnalyticsManager().bindIdentity('after-load');
    await DeviceHealthTelemetry.policySettled;
    raw.complete(jsonEncode({'audio_outage_started_at': DateTime(2026, 10, 9).millisecondsSinceEpoch}));
    await emission;
    expect(events, isEmpty);
    expect((await SharedPreferences.getInstance()).getString(DeviceHealthTelemetry.outageKey('late-import')), isNull);
  });

  test('same-account restart preserves durable identity epoch and outage', () async {
    AnalyticsManager().bindIdentity('same-account');
    await DeviceHealthTelemetry.policySettled;
    final epoch = AnalyticsManager.identityEpoch;
    await DeviceHealthTelemetry.recordOutage('same-account-device', at: DateTime(2026, 10, 9, 23));
    AnalyticsManager.resetForTesting();
    AnalyticsManager().bindIdentity('same-account');
    await DeviceHealthTelemetry.policySettled;
    expect(AnalyticsManager.identityEpoch, epoch);
    final prefs = await SharedPreferences.getInstance();
    final record = jsonDecode(prefs.getString(DeviceHealthTelemetry.outageKey('same-account-device'))!) as Map;
    expect(record['identity_epoch'], epoch);
    expect(record['open_since'], DateTime(2026, 10, 9, 23).millisecondsSinceEpoch);
  });

  test('sign-out sends native retirement before subsequent recording', () async {
    final policies = <Map>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(DeviceHealthTelemetry.policyChannel, (call) async {
      policies.add(call.arguments as Map);
      return null;
    });
    AnalyticsManager().bindIdentity('signed-in');
    await DeviceHealthTelemetry.policySettled;
    AnalyticsManager().bindIdentity(null);
    await DeviceHealthTelemetry.policySettled;
    expect(policies.last['retire'], isTrue);
    expect(policies.last['enabled'], isFalse);
    await DeviceHealthTelemetry.recordOutage('signed-out');
    expect((await SharedPreferences.getInstance()).getString(DeviceHealthTelemetry.outageKey('signed-out')), isNull);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(DeviceHealthTelemetry.policyChannel, null);
  });
}

Future<List<Map<String, dynamic>>> setupDelivery() async {
  debugDefaultTargetPlatformOverride = TargetPlatform.android;
  final delivered = <Map<String, dynamic>>[];
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(const MethodChannel('posthog_flutter'), (call) async {
    if (call.method == 'distinctId') return 'delivery-user';
    if (call.method == 'capture') {
      final args = call.arguments as Map;
      if (args['eventName'] == DeviceHealthTelemetry.eventName) {
        delivered.add(Map<String, dynamic>.from(args['properties'] as Map));
      }
    }
    return null;
  });
  PackageInfo.setMockInitialValues(
      appName: 'test', packageName: 'test', version: 'current', buildNumber: '3', buildSignature: '');
  AnalyticsManager.configure(PostHogAnalyticsAdapter(apiKey: 'hermetic'));
  AnalyticsManager().bindIdentity('delivery-user');
  await DeviceHealthTelemetry.policySettled;
  await AnalyticsManager.init();
  return delivered;
}

Future<void> drainDelivery() async {
  // A scheduled manager flush may already own the SDK serialization queue.
  for (var i = 0; i < 10; i++) {
    await Future<void>.delayed(const Duration(milliseconds: 10));
    await AnalyticsManager.flushPending(force: true);
  }
}
