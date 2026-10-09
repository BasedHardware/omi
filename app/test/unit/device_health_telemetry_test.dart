import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/device_health_telemetry.dart';

void main() {
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
    expect(result['audio_packet_loss_ratio'], 0.2);
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
}
