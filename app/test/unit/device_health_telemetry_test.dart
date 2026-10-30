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

  test('stale native outage on a connected device is not a full lost day', () async {
    final day = DateTime(2026, 10, 15);
    final start = day.millisecondsSinceEpoch;
    final poisoned = DeviceHealthTelemetry.rollup({
      'observed_at': start + 86400000,
      'outage_open_since': start - 86400000,
      'connected_at': start + 90000,
    }, day);
    expect(poisoned['connected_time_fraction'], greaterThan(0.99));
    expect(poisoned['lost_audio_seconds'], 90);
    expect(poisoned['unresolved_outage_seconds'], 90);

    const id = 'stale-connected';
    await DeviceHealthTelemetry.recordOutage(id, at: DateTime.fromMillisecondsSinceEpoch(start - 86400000));
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 16, 8),
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'observed_at': start + 86400000,
              'audio_outage_started_at': start - 86400000,
              'connected_at': start + 90000,
              'audio_packets_received': 5000,
              'audio_packet_days': [
                {'ts': start, 'received': 5000, 'expected': 5000, 'last_at': start + 3600000}
              ],
            }),
        emit: (_, props) => events.add(props));
    expect(events.map((e) => e['day']), ['2026-10-15']);
    expect(events.single['connected_time_fraction'], greaterThan(0.99));
    expect(events.single['lost_audio_seconds'], 90);
    expect(events.single['unresolved_outage_open'], isFalse);
    expect(events.single['lost_audio_seconds'], isNot(86400));
  });

  test('stalled Android retry does not close an open audio outage', () async {
    final day = DateTime(2026, 10, 15);
    final start = day.millisecondsSinceEpoch;
    final disconnectAt = start + 10 * 3600000;
    final retryAt = start + 12 * 3600000;
    const id = 'android-stalled-retry';
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 16, 8),
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'observed_at': retryAt,
              'audio_outage_started_at': disconnectAt,
              // Attempt start, before GATT. The previous session's counter is
              // still set; packet evidence is older than this attempt.
              'connected_at': retryAt,
              'audio_packets_received': 5000,
              'audio_packet_days': [
                {'ts': start, 'received': 5000, 'expected': 5000, 'last_at': disconnectAt - 1000}
              ],
              'disconnect_history_v2': [
                {
                  'timestamp': disconnectAt,
                  'eventType': 'disconnect',
                  'connectionDurationMs': 10 * 3600000,
                  'audioPacketsReceived': 5000,
                }
              ],
            }),
        emit: (_, props) => events.add(props));
    expect(events.map((e) => e['day']), ['2026-10-15']);
    expect(events.single['unresolved_outage_open'], isTrue);
    expect(events.single['lost_audio_seconds'], 2 * 3600);
    final record =
        jsonDecode((await SharedPreferences.getInstance()).getString(DeviceHealthTelemetry.outageKey(id))!) as Map;
    expect(record['open_since'], disconnectAt);
  });

  test('recovery stamp closes an outage while the start marker is still present', () async {
    const id = 'recovery-stamp';
    final start = DateTime(2026, 10, 15, 10);
    final resolved = DateTime(2026, 10, 15, 12);
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 16, 8),
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'observed_at': DateTime(2026, 10, 16).millisecondsSinceEpoch,
              'audio_outage_started_at': start.millisecondsSinceEpoch,
              'audio_outage_resolved_start': start.millisecondsSinceEpoch,
              'audio_outage_resolved_at': resolved.millisecondsSinceEpoch,
            }),
        emit: (_, props) => events.add(props));
    expect(events.single['unresolved_outage_open'], isFalse);
    expect(events.single['lost_audio_seconds'], 2 * 3600);
    final record =
        jsonDecode((await SharedPreferences.getInstance()).getString(DeviceHealthTelemetry.outageKey(id))!) as Map;
    expect(record['open_since'], isNull);
    expect(record['last_resolved_start'], start.millisecondsSinceEpoch);
  });

  test('fractional outage_open_since and observed_at do not bill or widen a day', () {
    final day = DateTime(2026, 10, 15);
    final start = day.millisecondsSinceEpoch;
    // observed_at truncation would extend the exposure window; a fractional
    // open_since would bill an outage boundary the writers never wrote.
    final rolled = DeviceHealthTelemetry.rollup({
      'observed_at': start + 20 * 3600000 + 0.5,
      'outage_open_since': start + 3600000 + 0.5,
      'disconnect_history_v2': [
        {'timestamp': start + 3600000, 'eventType': 'disconnect', 'connectionDurationMs': 60000},
      ],
    }, day);
    // The fractional open is malformed: it contributes no lost audio.
    expect(rolled['lost_audio_seconds'] ?? 0, 0);
    // The integer disconnect row still counts its minute of connection.
    final fraction = rolled['connected_time_fraction'] as num;
    // 60s of a 24h day is ~0.00069; a truncated-but-fractional window would
    // not reach it exactly, so require at least half the minute.
    expect(fraction, greaterThanOrEqualTo(0.0003));
  });

  test('fractional native outage start is not imported as an outage', () async {
    const id = 'fractional-native-start';
    final start = DateTime(2026, 10, 15, 10);
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 16, 8),
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'observed_at': DateTime(2026, 10, 16).millisecondsSinceEpoch,
              // Fractional native start: truncation would bill an outage the
              // writers never recorded.
              'audio_outage_started_at': start.millisecondsSinceEpoch + 0.5,
            }),
        emit: (_, props) => events.add(props));
    // The malformed start proves nothing: no outage record is written at all.
    expect((await SharedPreferences.getInstance()).getString(DeviceHealthTelemetry.outageKey(id)), isNull);
  });

  test('fractional audio_recovered history row is not imported as a resolution', () async {
    const id = 'fractional-history-row';
    final start = DateTime(2026, 10, 15, 10);
    final resolved = DateTime(2026, 10, 15, 12);
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 16, 8),
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'observed_at': DateTime(2026, 10, 16).millisecondsSinceEpoch,
              'audio_outage_started_at': start.millisecondsSinceEpoch,
              'disconnect_history_v2': [
                {
                  'eventType': 'audio_recovered',
                  'timestamp': start.millisecondsSinceEpoch + 0.5,
                  'lostAudioResolvedAt': resolved.millisecondsSinceEpoch + 0.5,
                }
              ],
            }),
        emit: (_, props) => events.add(props));
    // The malformed row proves nothing: the outage stays open.
    expect(events.single['unresolved_outage_open'], isTrue);
    final record =
        jsonDecode((await SharedPreferences.getInstance()).getString(DeviceHealthTelemetry.outageKey(id))!) as Map;
    expect(record['open_since'], start.millisecondsSinceEpoch);
  });

  test('fractional recovery stamp values never close an outage', () async {
    const id = 'fractional-stamp';
    final start = DateTime(2026, 10, 15, 10);
    final resolved = DateTime(2026, 10, 15, 12);
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 16, 8),
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'observed_at': DateTime(2026, 10, 16).millisecondsSinceEpoch,
              'audio_outage_started_at': start.millisecondsSinceEpoch,
              // 0.5 fractions must not truncate into the outage's exact
              // (start, at) pair: writers emit integer millis only.
              'audio_outage_resolved_start': start.millisecondsSinceEpoch + 0.5,
              'audio_outage_resolved_at': resolved.millisecondsSinceEpoch + 0.5,
            }),
        emit: (_, props) => events.add(props));
    expect(events.single['unresolved_outage_open'], isTrue);
    final record =
        jsonDecode((await SharedPreferences.getInstance()).getString(DeviceHealthTelemetry.outageKey(id))!) as Map;
    expect(record['open_since'], start.millisecondsSinceEpoch);
  });

  test('replayed days before the retention horizon exclude the unknown prefix', () {
    final day = DateTime(2026, 10, 9);
    final start = day.millisecondsSinceEpoch;
    final observedAt = DateTime(2026, 10, 16, 23).millisecondsSinceEpoch;
    final horizon = observedAt - 7 * 24 * 3600 * 1000;
    final survived = {
      'timestamp': horizon + 30 * 60 * 1000,
      'eventType': 'disconnect',
      'connectionDurationMs': 30 * 60 * 1000,
    };
    final withPackets = DeviceHealthTelemetry.rollup({
      'observed_at': observedAt,
      'outage_open_since': start,
      'audio_packet_days': [
        {'ts': start, 'received': 100, 'expected': 100, 'last_at': start + 22 * 3600000}
      ],
      'disconnect_history_v2': [survived],
    }, day);
    expect(withPackets['connection_history_incomplete'], isTrue);
    expect(withPackets['lost_audio_seconds'], 30 * 60);
    expect(withPackets['unresolved_outage_open'], isTrue);
    // No packet row: the pruned prefix is still unknown budget, and the
    // outage stays open. The surviving 30 minutes after the horizon remain.
    final withoutPackets = DeviceHealthTelemetry.rollup({
      'observed_at': observedAt,
      'outage_open_since': start,
      'disconnect_history_v2': [survived],
    }, day);
    expect(withoutPackets['connection_history_incomplete'], isTrue);
    expect(withoutPackets['lost_audio_seconds'], 30 * 60);
    expect(withoutPackets['unresolved_outage_open'], isTrue);
  });

  test('unbacked audio recovery is not imported and its persisted day is kept', () async {
    const id = 'stale-false-recovery';
    final falseDay = DateTime(2026, 10, 14, 10);
    final backedDay = DateTime(2026, 10, 15, 12);
    await DeviceHealthTelemetry.recordOutage(id, at: falseDay);
    await DeviceHealthTelemetry.recordRecovery(id, at: falseDay.add(const Duration(hours: 2)));
    await DeviceHealthTelemetry.recordOutage(id, at: backedDay);
    await DeviceHealthTelemetry.recordRecovery(id, at: backedDay.add(const Duration(seconds: 60)));
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('device_health_day_$id', '2026-10-13');
    final backedStart = backedDay.millisecondsSinceEpoch;
    final falseStart = falseDay.millisecondsSinceEpoch;
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 16, 8),
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'observed_at': DateTime(2026, 10, 16).millisecondsSinceEpoch,
              'disconnect_history_v2': [
                {
                  'timestamp': falseStart,
                  'eventType': 'audio_recovered',
                  'lostAudioResolvedAt': falseStart + 2 * 3600000,
                },
                {
                  'timestamp': backedStart,
                  'eventType': 'disconnect',
                  'lostAudioResolvedAt': backedStart + 60000,
                },
              ],
            }),
        emit: (_, props) => events.add(props));
    expect(events.map((e) => e['day']), ['2026-10-14', '2026-10-15']);
    expect(events.first['lost_audio_seconds'], 2 * 3600);
    expect(events.last['lost_audio_seconds'], 60);
  });

  test('standalone audio recovery backed by a native stamp is imported', () async {
    const id = 'stamped-standalone-recovery';
    final start = DateTime(2026, 10, 15, 12).millisecondsSinceEpoch;
    final resolved = start + 60000;
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 16, 8),
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'observed_at': DateTime(2026, 10, 16).millisecondsSinceEpoch,
              'disconnect_history_v2': [
                {
                  'timestamp': start,
                  'eventType': 'audio_recovered',
                  'lostAudioResolvedAt': resolved,
                },
              ],
              'audio_outage_resolved_start': start,
              'audio_outage_resolved_at': resolved,
            }),
        emit: (_, props) => events.add(props));
    expect(events.single['lost_audio_seconds'], 60);
    final record =
        jsonDecode((await SharedPreferences.getInstance()).getString(DeviceHealthTelemetry.outageKey(id))!) as Map;
    expect(record['last_resolved_start'], start);
  });

  test('audio recovery with neither disconnect nor stamp is dropped', () async {
    const id = 'unproven-audio-recovered';
    final start = DateTime(2026, 10, 15, 12).millisecondsSinceEpoch;
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 16, 8),
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'observed_at': DateTime(2026, 10, 16).millisecondsSinceEpoch,
              'disconnect_history_v2': [
                {
                  'timestamp': start,
                  'eventType': 'audio_recovered',
                  'lostAudioResolvedAt': start + 2 * 3600000,
                },
              ],
            }),
        emit: (_, props) => events.add(props));
    expect(events, isEmpty);
    expect((await SharedPreferences.getInstance()).getString(DeviceHealthTelemetry.outageKey(id)), isNull);
  });

  test('a native stamp does not import a different standalone recovery', () async {
    const id = 'stamp-mismatch';
    final rowStart = DateTime(2026, 10, 15, 10).millisecondsSinceEpoch;
    final stampStart = DateTime(2026, 10, 15, 14).millisecondsSinceEpoch;
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 16, 8),
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'observed_at': DateTime(2026, 10, 16).millisecondsSinceEpoch,
              'disconnect_history_v2': [
                {
                  'timestamp': rowStart,
                  'eventType': 'audio_recovered',
                  'lostAudioResolvedAt': rowStart + 2 * 3600000,
                },
              ],
              'audio_outage_resolved_start': stampStart,
              'audio_outage_resolved_at': stampStart + 60000,
            }),
        emit: (_, props) => events.add(props));
    expect(events.single['lost_audio_seconds'], 60);
  });

  test('every native recovery proof imports its standalone row', () async {
    const id = 'two-standalone-proofs';
    final first = DateTime(2026, 10, 15, 12).millisecondsSinceEpoch;
    final second = DateTime(2026, 10, 15, 14).millisecondsSinceEpoch;
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 16, 8),
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'observed_at': DateTime(2026, 10, 16).millisecondsSinceEpoch,
              'audio_outage_resolved_start': second,
              'audio_outage_resolved_at': second + 120000,
              'audio_outage_recovery_proofs': [
                {'start': first, 'at': first + 60000},
                {'start': second, 'at': second + 120000},
              ],
              'disconnect_history_v2': [
                {'timestamp': first, 'eventType': 'audio_recovered', 'lostAudioResolvedAt': first + 60000},
                {'timestamp': second, 'eventType': 'audio_recovered', 'lostAudioResolvedAt': second + 120000},
              ],
            }),
        emit: (_, props) => events.add(props));
    expect(events.single['lost_audio_seconds'], 180);
  });

  test('a mixed false and real recovery day is left intact', () async {
    const id = 'mixed-recovery-day';
    final falseStartAt = DateTime(2026, 10, 15, 10);
    final falseStart = falseStartAt.millisecondsSinceEpoch;
    final realStart = falseStart + 3 * 3600000;
    await DeviceHealthTelemetry.recordOutage(id, at: falseStartAt);
    await DeviceHealthTelemetry.recordRecovery(id, at: falseStartAt.add(const Duration(hours: 2)));
    await DeviceHealthTelemetry.recordOutage(id, at: DateTime.fromMillisecondsSinceEpoch(realStart));
    await DeviceHealthTelemetry.recordRecovery(id, at: DateTime.fromMillisecondsSinceEpoch(realStart + 60000));
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('device_health_day_$id', '2026-10-14');
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 16, 8),
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'observed_at': DateTime(2026, 10, 16).millisecondsSinceEpoch,
              'disconnect_history_v2': [
                {
                  'timestamp': falseStart,
                  'eventType': 'audio_recovered',
                  'lostAudioResolvedAt': falseStart + 2 * 3600000,
                },
                {
                  'timestamp': realStart,
                  'eventType': 'disconnect',
                  'lostAudioResolvedAt': realStart + 60000,
                },
              ],
            }),
        emit: (_, props) => events.add(props));
    expect(events.single['lost_audio_seconds'], 7260);
    final record =
        jsonDecode((await SharedPreferences.getInstance()).getString(DeviceHealthTelemetry.outageKey(id))!) as Map;
    expect((record['resolved_days'] as Map)[DateTime(2026, 10, 15).millisecondsSinceEpoch.toString()], 7260);
  });

  test('an aged-out native recovery does not delete the persisted day', () async {
    const id = 'aged-out-native-recovery';
    final observedAt = DateTime(2026, 10, 16, 8);
    // Native history and recovery proofs expire after seven days. This recovery
    // ended before that horizon; Dart still emits the calendar day.
    const nativeRetentionMs = 7 * 24 * 3600 * 1000;
    final horizon = observedAt.millisecondsSinceEpoch - nativeRetentionMs;
    final resolvedAt = DateTime.fromMillisecondsSinceEpoch(horizon - 3600000);
    final start = resolvedAt.subtract(const Duration(hours: 2));
    expect(resolvedAt.millisecondsSinceEpoch, lessThan(horizon));
    await DeviceHealthTelemetry.recordOutage(id, at: start);
    await DeviceHealthTelemetry.recordRecovery(id, at: resolvedAt);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('device_health_day_$id', '2026-10-08');
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: observedAt,
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'observed_at': observedAt.millisecondsSinceEpoch,
              'disconnect_history_v2': [],
            }),
        emit: (_, props) => events.add(props));
    expect(events.single['day'], '2026-10-09');
    expect(events.single['lost_audio_seconds'], 2 * 3600);
    final record =
        jsonDecode((await SharedPreferences.getInstance()).getString(DeviceHealthTelemetry.outageKey(id))!) as Map;
    expect(
        (record['resolved_days'] as Map).containsKey(DateTime(2026, 10, 9).millisecondsSinceEpoch.toString()), isTrue);
  });

  test('importing the same native proofs twice does not double count', () async {
    const id = 'proofs-twice';
    final first = DateTime(2026, 10, 15, 12).millisecondsSinceEpoch;
    final second = DateTime(2026, 10, 15, 14).millisecondsSinceEpoch;
    Future<String> load(_) async => jsonEncode({
          'observed_at': DateTime(2026, 10, 16).millisecondsSinceEpoch,
          'audio_outage_resolved_start': second,
          'audio_outage_resolved_at': second + 120000,
          'audio_outage_recovery_proofs': [
            {'start': first, 'at': first + 60000},
            {'start': second, 'at': second + 120000},
          ],
          'disconnect_history_v2': [
            {'timestamp': first, 'eventType': 'audio_recovered', 'lostAudioResolvedAt': first + 60000},
            {'timestamp': second, 'eventType': 'audio_recovered', 'lostAudioResolvedAt': second + 120000},
          ],
        });
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 16, 8),
        emissionContext: {},
        loadDiagnostics: load,
        emit: (_, props) => events.add(props));
    expect(events.single['lost_audio_seconds'], 180);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('device_health_day_$id', '2026-10-14');
    events.clear();
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 16, 8),
        emissionContext: {},
        loadDiagnostics: load,
        emit: (_, props) => events.add(props));
    expect(events.single['lost_audio_seconds'], 180);
    final record = jsonDecode(prefs.getString(DeviceHealthTelemetry.outageKey(id))!) as Map;
    expect((record['resolved_days'] as Map)[DateTime(2026, 10, 15).millisecondsSinceEpoch.toString()], 180);
  });

  test('audio recovery backed by a disconnect is imported', () async {
    const id = 'backed-audio-recovered';
    final start = DateTime(2026, 10, 15, 12).millisecondsSinceEpoch;
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 16, 8),
        emissionContext: {},
        loadDiagnostics: (_) async => jsonEncode({
              'observed_at': DateTime(2026, 10, 16).millisecondsSinceEpoch,
              'disconnect_history_v2': [
                {'timestamp': start, 'eventType': 'disconnect'},
                {
                  'timestamp': start + 1000,
                  'eventType': 'audio_recovered',
                  'lostAudioResolvedAt': start + 61000,
                },
              ],
            }),
        emit: (_, props) => events.add(props));
    expect(events.single['lost_audio_seconds'], 60);
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
