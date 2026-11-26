import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/device_dropoff_signals.dart';
import 'package:omi/utils/analytics/device_health_telemetry.dart';

const _minute = 60 * 1000;
const _hour = 60 * _minute;

void main() {
  final day = DateTime(2026, 11, 20);
  final start = day.millisecondsSinceEpoch;
  final nextDay = DateTime(2026, 11, 21).millisecondsSinceEpoch;

  Map<String, dynamic> disconnect(
    int at, {
    int durationMs = 2 * _hour,
    int? packets = 500,
    String reason = 'connection_timeout',
    bool manual = false,
    int rssi = -60,
    int rssiAgeMs = 5000,
    String trend = 'sudden',
    int timeToReconnectMs = 0,
  }) =>
      {
        'timestamp': at,
        'eventType': 'disconnect',
        'reason': reason,
        'isManual': manual,
        'lastRssi': rssi,
        'lastRssiAgeMs': rssiAgeMs,
        'rssiTrend': trend,
        'connectionDurationMs': durationMs,
        'audioPacketsReceived': packets,
        'timeToReconnectMs': timeToReconnectMs,
      };

  Map<String, dynamic> battery(int at, int level, {bool? charging}) =>
      {'ts': at, 'level': level, if (charging != null) 'charging': charging};

  group('gap cause', () {
    Map<String, dynamic> rowAt(
            {String reason = 'connection_timeout', int rssi = -60, int age = 5000, String trend = 'sudden'}) =>
        disconnect(start + 10 * _hour, reason: reason, rssi: rssi, rssiAgeMs: age, trend: trend);

    test('reason-backed causes win over signal and battery', () {
      expect(DeviceDropoffSignals.cause(disconnect(start, manual: true), battery(start, 1)), 'manual');
      expect(DeviceDropoffSignals.cause(rowAt(reason: 'pairing_lost'), null), 'pairing_lost');
      expect(DeviceDropoffSignals.cause(rowAt(reason: 'bluetooth_off'), null), 'phone_side');
    });

    test('a recent low uncharged level is a flat battery; charging or stale is not', () {
      final row = rowAt();
      final ts = row['timestamp'] as int;
      expect(DeviceDropoffSignals.cause(row, battery(ts - 30 * _minute, 4)), 'battery_flat');
      expect(DeviceDropoffSignals.cause(row, battery(ts - 30 * _minute, 4, charging: true)), 'power_off');
      expect(DeviceDropoffSignals.cause(row, battery(ts - 2 * _hour, 4)), 'power_off');
      expect(DeviceDropoffSignals.cause(row, battery(ts - 30 * _minute, 6)), 'power_off');
    });

    test('fresh RSSI separates walking away from an abrupt loss at strong signal', () {
      expect(DeviceDropoffSignals.cause(rowAt(rssi: -92), null), 'out_of_range');
      expect(DeviceDropoffSignals.cause(rowAt(rssi: -70, trend: 'fading'), null), 'out_of_range');
      expect(DeviceDropoffSignals.cause(rowAt(rssi: -60), null), 'power_off');
      expect(DeviceDropoffSignals.cause(rowAt(rssi: -80), null), 'unknown');
      expect(DeviceDropoffSignals.cause(rowAt(rssi: -60, age: 45000), null), 'unknown');
      expect(DeviceDropoffSignals.cause({...rowAt(rssi: -60)}..remove('lastRssiAgeMs'), null), 'unknown');
      expect(DeviceDropoffSignals.cause(rowAt(rssi: 0), null), 'unknown');
    });
  });

  test('short reconnects are not gaps; the latest gap before day end carries battery and attempts', () {
    final gapAt = start + 20 * _hour;
    final result = DeviceDropoffSignals.rollup({
      'observed_at': nextDay + 9 * _hour,
      'disconnect_history_v2': [
        disconnect(start + 8 * _hour, rssi: -95, timeToReconnectMs: 10 * _minute),
        disconnect(start + 12 * _hour, rssi: -95, timeToReconnectMs: 45 * _minute),
        disconnect(gapAt, rssi: -58),
        {'timestamp': gapAt + _hour, 'eventType': 'fail_to_connect', 'reason': 'connection_failed_instant_passed'},
        {'timestamp': gapAt - _hour, 'eventType': 'fail_to_connect', 'reason': 'connection_failed_instant_passed'},
      ],
      'battery_history_v2': [battery(gapAt - 3 * _hour, 62), battery(gapAt - 20 * _minute, 41, charging: false)],
    }, day);
    expect(result['long_gaps'], 2);
    expect(result['long_gaps_by_cause'], {'out_of_range': 1, 'power_off': 1});
    expect(result['gap_cause'], 'power_off');
    expect(result['gap_battery_level'], 41);
    expect(result['gap_battery_age_min'], 20);
    expect(result['gap_battery_charging'], false);
    expect(result['gap_last_rssi'], -58);
    expect(result['gap_rssi_age_s'], 5);
    expect(result['gap_rssi_trend'], 'sudden');
    expect(result['gap_fail_to_connect'], 1);
    expect(result['gap_age_hours'], 4);
    expect(result['gap_minutes'], 240);
    expect(result['gap_open_at_day_end'], true);
    // Android snapshots carry no reconnect-scan log: no scan fields, not zeros.
    expect(result.containsKey('gap_advert_sightings'), isFalse);
  });

  test('a fully disconnected later day carries the open gap forward', () {
    final gapAt = start + 22 * _hour;
    final later = DateTime(2026, 11, 22);
    final result = DeviceDropoffSignals.rollup({
      'observed_at': DateTime(2026, 11, 23, 8).millisecondsSinceEpoch,
      'disconnect_history_v2': [disconnect(gapAt, rssi: -91)],
      'battery_history_v2': [battery(gapAt - 10 * _minute, 73)],
      'saved_reconnect_enabled': true,
      'reconnect_suppressed': false,
    }, later);
    expect(result['long_gaps'], 0);
    expect(result['gap_cause'], 'out_of_range');
    expect(result['gap_battery_level'], 73);
    expect(result['gap_age_hours'], 50);
    expect(result['gap_open_at_day_end'], true);
    expect(result['gap_saved_reconnect_enabled'], true);
    expect(result['gap_reconnect_suppressed'], false);
    // The iOS log keeps 24 h; it cannot reach back to a gap two days old.
    expect(result['gap_advert_sightings'], isNull);
    expect(result['gap_scan_windows'], isNull);
  });

  test('a gap that ended before day end is closed and drops the reconnect snapshot', () {
    final gapAt = start + 2 * _hour;
    final result = DeviceDropoffSignals.rollup({
      'observed_at': nextDay + _hour,
      'disconnect_history_v2': [
        disconnect(gapAt, manual: true),
        disconnect(start + 9 * _hour, durationMs: 4 * _hour, rssi: -40, timeToReconnectMs: _minute),
      ],
      'saved_reconnect_enabled': true,
    }, day);
    expect(result['gap_cause'], 'manual');
    expect(result['gap_minutes'], 180);
    expect(result['gap_open_at_day_end'], false);
    expect(result.containsKey('gap_saved_reconnect_enabled'), isFalse);
  });

  test('a gap still under 30 minutes at observation is not a gap yet', () {
    final result = DeviceDropoffSignals.rollup({
      'observed_at': start + 10 * _hour + 20 * _minute,
      'disconnect_history_v2': [disconnect(start + 10 * _hour, rssi: -95)],
    }, day);
    expect(result['long_gaps'], 0);
    expect(result.containsKey('gap_cause'), isFalse);
  });

  test('iOS reconnect-scan sightings inside the gap are counted when the log covers it', () {
    final gapAt = start + 20 * _hour;
    final result = DeviceDropoffSignals.rollup({
      'observed_at': nextDay + 8 * _hour,
      'disconnect_history_v2': [disconnect(gapAt, rssi: -60)],
      'saved_reconnect_enabled': true,
      'ble_log': [
        {'ts': gapAt - _minute, 'event': 'reconnect_scan_result', 'detail': 'saved_target=true,rssi=-60'},
        {'ts': gapAt + 100, 'event': 'reconnect_scan_started', 'detail': 'diagnostic:5s:service_filtered'},
        {'ts': gapAt + 2000, 'event': 'reconnect_scan_result', 'detail': 'saved_target=false,rssi=-70'},
        {'ts': gapAt + 3000, 'event': 'reconnect_scan_result', 'detail': 'saved_target=true,rssi=-88'},
      ],
    }, day);
    expect(result['gap_scan_windows'], 1);
    expect(result['gap_advert_sightings'], 1);
  });

  test('connected time without audio is split from disconnected time, only for streaming devices', () {
    final diagnostics = {
      'observed_at': nextDay + _hour,
      'disconnect_history_v2': [
        disconnect(start + 3 * _hour, durationMs: 2 * _hour, packets: 0, timeToReconnectMs: _minute),
        disconnect(start + 6 * _hour, durationMs: 2 * _hour, packets: 9000, timeToReconnectMs: _minute),
        disconnect(start + 7 * _hour, durationMs: 30 * 1000, packets: 0, timeToReconnectMs: _minute),
        disconnect(start + 2 * _hour, durationMs: 4 * _hour, packets: null, timeToReconnectMs: _minute),
      ],
    };
    final result = DeviceDropoffSignals.rollup(diagnostics, day);
    expect(result['connected_no_audio_seconds'], 2 * 3600);
    expect(result['connected_no_audio_sessions'], 1);

    final neverStreams = DeviceDropoffSignals.rollup({
      'disconnect_history_v2': [disconnect(start + 3 * _hour, packets: 0)],
    }, day);
    expect(neverStreams.containsKey('connected_no_audio_seconds'), isFalse);
  });

  test('charging is inferred from a rising run, once, on the day it crosses the threshold', () {
    final result = DeviceDropoffSignals.rollup({
      'battery_history_v2': [
        battery(start - _hour, 30),
        battery(start + _hour, 28),
        battery(start + 2 * _hour, 29),
        battery(start + 3 * _hour, 31),
        battery(start + 4 * _hour, 34),
        battery(start + 5 * _hour, 60),
        battery(start + 6 * _hour, 59),
        battery(start + 7 * _hour, 60),
        battery(start + 9 * _hour, 98),
      ],
    }, day);
    expect(result['charge_inferred_events'], 2);
    expect(result['battery_min_level'], 28);
    expect(result['battery_max_level'], 98);
    final jitter = DeviceDropoffSignals.rollup({
      'battery_history_v2': [battery(start, 50), battery(start + _hour, 52), battery(start + 2 * _hour, 49)],
    }, day);
    expect(jitter['charge_inferred_events'], 0);
  });

  test('daily rollup reports schema 3 split fields, and the kill-switch shape is schema 2', () {
    final diagnostics = {
      'observed_at': nextDay + _hour,
      'disconnect_history_v2': [disconnect(start + 6 * _hour, durationMs: 3 * _hour, packets: 5400)],
      'audio_packet_days': [
        {'ts': start, 'received': 5400, 'expected': 5400},
      ],
    };
    final on = DeviceHealthTelemetry.rollup(diagnostics, day);
    expect(on['schema_version'], 3);
    expect(on['connected_seconds'], 3 * 3600);
    expect(on['disconnected_seconds'], 21 * 3600);
    expect(on['audio_packets_per_connected_minute'], 30);
    expect(on['connected_no_audio_seconds'], 0);
    final off = DeviceHealthTelemetry.rollup(diagnostics, day, dropoff: false);
    expect(off['schema_version'], 2);
    expect(off.keys.toSet().intersection({'connected_seconds', 'gap_cause', 'long_gaps', 'charge_inferred_events'}),
        isEmpty);
    expect(on.keys.toSet().containsAll(off.keys.toSet()), isTrue);
  });

  group('emitter kill switch', () {
    setUp(() async {
      await DeviceHealthTelemetry.policySettled;
      AnalyticsManager.resetForTesting();
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });
    tearDown(() async {
      await DeviceHealthTelemetry.policySettled;
      AnalyticsManager.resetForTesting();
    });

    Future<Map<String, dynamic>> emitOnce(String id, Future<bool> Function() disabled) async {
      final emitted = <Map<String, dynamic>>[];
      await DeviceHealthTelemetry.maybeEmit(
        BtDevice.empty().copyWith(id: id),
        now: DateTime(2026, 11, 21, 9),
        emissionContext: {},
        dropoffDisabled: disabled,
        loadDiagnostics: (_) async => jsonEncode({
          'observed_at': DateTime(2026, 11, 21, 9).millisecondsSinceEpoch,
          'disconnect_history_v2': [disconnect(start + 20 * _hour, rssi: -95)],
        }),
        emit: (_, properties) => emitted.add(properties),
      );
      expect(emitted, hasLength(1));
      return emitted.single;
    }

    test('on by default, off when the flag is true, on when the read fails', () async {
      final on = await emitOnce('dropoff-on', () async => false);
      expect(on['schema_version'], 3);
      expect(on['gap_cause'], 'out_of_range');
      final off = await emitOnce('dropoff-off', () async => true);
      expect(off['schema_version'], 2);
      expect(off.containsKey('gap_cause'), isFalse);
      final unreadable = await emitOnce('dropoff-unreadable', () async => throw StateError('flags'));
      expect(unreadable['schema_version'], 3);
    });
  });
}
