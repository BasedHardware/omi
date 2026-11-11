import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/background_resource_telemetry.dart';

void main() {
  const startSnapshot = BackgroundResourceSnapshot(
    bleBytesReceived: 100,
    websocketBytesSent: 50,
    recordingState: 'deviceRecord',
    deviceConnected: true,
    deviceType: 'omi',
    batchModeEnabled: false,
    diagnosticsDeviceId: 'device-1',
  );

  test('emits one bounded summary with resource deltas after a real background session', () async {
    var now = DateTime.utc(2026, 8, 19, 12);
    String? emittedName;
    Map<String, dynamic>? emittedProperties;
    final telemetry = BackgroundResourceTelemetry(
      emit: (name, properties) {
        emittedName = name;
        emittedProperties = properties;
      },
      now: () => now,
      sessionIdFactory: () => 'session-1',
    );

    telemetry.onPaused(startSnapshot);
    // Duplicate lifecycle callbacks must not replace the original baseline.
    now = now.add(const Duration(seconds: 30));
    telemetry.onPaused(startSnapshot);
    now = now.add(const Duration(seconds: 90));
    await telemetry.onResumed(
      (_, start) async {
        expect(start.diagnosticsDeviceId, 'device-1');
        return const BackgroundResourceSnapshot(
          bleBytesReceived: 1300,
          websocketBytesSent: 650,
          recordingState: 'deviceRecord',
          deviceConnected: true,
          deviceType: 'omi',
          batchModeEnabled: false,
          foregroundTaskRunning: false,
          backgroundDisconnectCount: 3,
          connectionTimeoutCount: 2,
          failToConnectCount: 1,
          reconnectCount: 2,
          maxReconnectDurationMs: 4200,
          reconnectionCountTotal: 11,
          failToConnectCountTotal: 5,
          bleHistorySaturated: true,
          nativeBackgroundBytesConsumed: 4200,
          nativeBackgroundPacketsConsumed: 42,
        );
      },
    );

    expect(emittedName, BackgroundResourceTelemetry.eventName);
    expect(emittedProperties, {
      'background_session_id': 'session-1',
      'background_duration_seconds': 120,
      'start_recording_state': 'deviceRecord',
      'end_recording_state': 'deviceRecord',
      'start_device_connected': true,
      'end_device_connected': true,
      'start_device_type': 'omi',
      'end_device_type': 'omi',
      'batch_mode_enabled': false,
      'ble_bytes_received': 1200,
      'websocket_bytes_sent': 600,
      'ble_receive_bytes_per_second': 10,
      'websocket_send_bytes_per_second': 5,
      'foreground_task_running_on_resume': false,
      'background_disconnect_count': 3,
      'connection_timeout_count': 2,
      'fail_to_connect_count': 1,
      'reconnect_count': 2,
      'max_reconnect_duration_ms': 4200,
      'reconnection_count_total': 11,
      'fail_to_connect_count_total': 5,
      'ble_history_saturated': true,
      'native_background_bytes_consumed': 4200,
      'native_background_packets_consumed': 42,
    });
  });

  test('suppresses short sessions and clamps counters that reset', () async {
    var now = DateTime.utc(2026, 8, 19, 12);
    final events = <Map<String, dynamic>>[];
    final telemetry = BackgroundResourceTelemetry(
      emit: (_, properties) => events.add(properties),
      now: () => now,
      sessionIdFactory: () => 'session-2',
    );

    telemetry.onPaused(startSnapshot);
    now = now.add(const Duration(seconds: 59));
    await telemetry.onResumed((_, __) async => startSnapshot);
    expect(events, isEmpty);

    telemetry.onPaused(startSnapshot);
    now = now.add(const Duration(minutes: 1));
    await telemetry.onResumed(
      (_, __) async => const BackgroundResourceSnapshot(
        bleBytesReceived: 0,
        websocketBytesSent: 0,
        recordingState: 'stop',
        deviceConnected: false,
        deviceType: 'none',
        batchModeEnabled: false,
      ),
    );
    expect(events.single['ble_bytes_received'], 0);
    expect(events.single['websocket_bytes_sent'], 0);
  });

  test('snapshot and emitter failures are fail-open and session state recovers', () async {
    var now = DateTime.utc(2026, 8, 19, 12);
    final telemetry = BackgroundResourceTelemetry(
      emit: (_, __) => throw StateError('analytics unavailable'),
      now: () => now,
    );

    telemetry.onPaused(startSnapshot);
    now = now.add(const Duration(minutes: 2));
    await expectLater(
      telemetry.onResumed((_, __) async => throw StateError('snapshot unavailable')),
      completes,
    );

    telemetry.onPaused(startSnapshot);
    now = now.add(const Duration(minutes: 2));
    await expectLater(telemetry.onResumed((_, __) async => startSnapshot), completes);
  });
}
