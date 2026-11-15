import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/pages/settings/device_diagnostics.dart';
import 'package:omi/services/bridges/ble_bridge.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const device = 'feedback-diagnostics';
  final bridge = BleBridge.instance;
  final now = DateTime.fromMillisecondsSinceEpoch(10000);

  Map<String, dynamic> bundle([Map<String, dynamic> native = const {}]) => feedbackDiagnosticsExportFields(
        native,
        captureHealth: bridge.diagnosticsCaptureHealth(device, observedAt: now),
      );

  void health({String phase = 'flowing', int validUntil = 20000, int lastAudio = 9000}) {
    bridge.onCaptureHealth(
        device,
        jsonEncode({
          'phase': phase,
          'generation': 'link-2',
          'reason': 'audio',
          'valid_until_ms': validUntil,
          'subscription_confirmed': true,
          'unverified_since_ms': 0,
          'last_audio_at_ms': lastAudio,
          'raw_payload': 'never export this',
          'description': 'never export this either',
        }));
  }

  tearDown(() => bridge.onCaptureHealth(device, 'null'));

  test('absent and malformed health stay unknown and history is explicitly unavailable', () {
    for (final snapshot in ['null', 'garbage', '{}']) {
      bridge.onCaptureHealth(device, snapshot);
      expect(bundle()['capture_health'], isNull);
      expect(bundle()['capture_health_history'], isNull);
      expect(bundle()['capture_health_history_status'], 'unavailable');
    }
  });

  test('present health uses the bridge allowlist and evaluates the lease at export time', () {
    health();
    final exported = bundle()['capture_health'] as Map;
    expect(exported['observed_at_ms'], 10000);
    expect(exported['verified'], true);
    expect(exported['audio_lease_valid'], true);
    expect(exported['generation'], 'link-2');
    expect(jsonEncode(exported), isNot(contains('never export')));
    expect(exported, isNot(contains('verified_at')));
  });

  test('expired flowing and healthy quiet are distinct', () {
    health(validUntil: 9999);
    expect((bundle()['capture_health'] as Map)['verified'], false);
    expect((bundle()['capture_health'] as Map)['audio_lease_valid'], false);
    health(phase: 'quiet', validUntil: 9999);
    expect((bundle()['capture_health'] as Map)['verified'], true);
    expect((bundle()['capture_health'] as Map)['audio_lease_valid'], false);
    health(phase: 'quiet', validUntil: 9999, lastAudio: 0);
    expect((bundle()['capture_health'] as Map)['verified'], false);
  });

  test('schema 2 history keeps charging and reconnect truth with missing audio age unknown', () {
    final native = jsonDecode('''{
      "schema_version":2,
      "battery_history_v2":[{"ts":1,"level":42,"charging":null},{"ts":2,"level":43,"charging":true}],
      "disconnect_history_v2":[{"timestamp":1,"reason":"remote_device_terminated","reasonCode":19,
        "timeToReconnectMs":50,"audioRecoveredAtMs":99}]
    }''') as Map<String, dynamic>;
    final exported = bundle(native);
    expect(exported['schema_version'], 3);
    expect(exported['battery_history'], native['battery_history_v2']);
    final event = (exported['disconnect_history'] as List).single as Map;
    expect(event['code'], 19);
    expect(event['reason'], 'remote_device_terminated');
    expect(event['time_to_reconnect_ms'], 50);
    expect(event['last_audio_notification_age_ms'], isNull);
    expect(event['lost_audio_seconds'], isNull);
    expect(exported['process_exit_collection'], isNull);
    expect(exported['firmware_diagnostics_read'], isNull);
    final fallback = feedbackDiagnosticsExportFields({},
        captureHealth: null, batteryHistory: [BleBatteryPoint(timestamp: 1, level: 42)]);
    expect((fallback['battery_history'] as List).single['charging'], isNull);
  });

  test('firmware outcome is independent of an empty ring and age does not declare lost audio', () {
    for (final outcome in ['attempted', 'succeeded', 'timeout', 'rejected', 'unsupported', 'skipped']) {
      final exported = bundle({
        'firmware_diagnostics_read': {'outcome': outcome, 'parse_outcome': 'not_attempted'},
        'disconnect_history_v2': [
          {'lastAudioNotificationAgeMs': 500, 'reasonCode': 19}
        ],
      });
      expect((exported['firmware_diagnostics_read'] as Map)['outcome'], outcome);
      final event = (exported['disconnect_history'] as List).single as Map;
      expect(event['last_audio_notification_age_ms'], 500);
      expect(event['lost_audio_seconds'], isNull);
    }
  });
}
