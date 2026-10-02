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
  });
}
