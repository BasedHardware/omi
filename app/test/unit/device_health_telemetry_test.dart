import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/device_health_telemetry.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    SharedPreferences.setMockInitialValues({});
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
  test('never recovered outage emits loss after restart, capped per device day', () async {
    final day = DateTime(2026, 10, 9);
    final start = day.millisecondsSinceEpoch;
    const id = 'unresolved-restart';
    // Seed only the durable record: no in-memory disconnect/recovery state.
    SharedPreferences.setMockInitialValues({
      DeviceHealthTelemetry.outageKey(id): jsonEncode({'open_since': start - 86400000}),
      'device_health_day_$id': '2026-10-08',
    });
    final events = <Map<String, dynamic>>[];
    await DeviceHealthTelemetry.maybeEmit(BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 10, 10),
        loadDiagnostics: (_) async => '{}',
        emissionContext: {'app_build': 'new+2'},
        emit: (_, properties) => events.add(properties));
    expect(events, hasLength(1));
    expect(events.single['lost_audio_seconds'], 86400);
    expect(events.single['unresolved_outage_seconds'], 86400);
    expect(events.single['unresolved_outage_open'], isTrue);
    expect(events.single['schema_version'], 2);
  });

  test('first recovered packet resolves durable outage after process death as today', () async {
    final start = DateTime(2026, 10, 9, 23, 59);
    const id = 'recovered-restart';
    SharedPreferences.setMockInitialValues({
      DeviceHealthTelemetry.outageKey(id): jsonEncode({'open_since': start.millisecondsSinceEpoch}),
    });
    await DeviceHealthTelemetry.recordRecovery(id, at: DateTime(2026, 10, 10, 0, 1));
    final prefs = await SharedPreferences.getInstance();
    final record = jsonDecode(prefs.getString(DeviceHealthTelemetry.outageKey(id))!) as Map;
    expect(record.containsKey('open_since'), isFalse);
    final result =
        DeviceHealthTelemetry.rollup({'outage_resolved_days': record['resolved_days']}, DateTime(2026, 10, 10));
    expect(result['lost_audio_seconds'], 120);
    expect(result['unresolved_outage_open'], isFalse);
    expect(result['unresolved_outage_seconds'], isNull);
  });

  test('backfilled emission uses observation build and firmware, skips missing days', () async {
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
        emit: (_, properties) => events.add(properties));
    expect(events.map((e) => e['day']), ['2026-10-08', '2026-10-10']);
    expect(events.first['day_app_build'], ['old+1']);
    expect(events.first['day_firmware'], ['fw1']);
    expect(events.first['firmware'], 'fw1');
    expect(events.last['day_app_build'], ['new+2']);
    expect(events.last['day_firmware'], isNull);
    expect(events.first['os_version'], isNull);
  });

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
    }
  });
}
