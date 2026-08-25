import 'dart:math' as math;

typedef BackgroundResourceEventEmitter = void Function(String eventName, Map<String, dynamic> properties);
typedef BackgroundResourceSnapshotLoader = Future<BackgroundResourceSnapshot> Function(
  DateTime backgroundStartedAt,
  BackgroundResourceSnapshot startSnapshot,
);

class BackgroundResourceSnapshot {
  const BackgroundResourceSnapshot({
    required this.bleBytesReceived,
    required this.websocketBytesSent,
    required this.recordingState,
    required this.deviceConnected,
    required this.deviceType,
    required this.batchModeEnabled,
    this.foregroundTaskRunning = false,
    this.backgroundDisconnectCount = 0,
    this.connectionTimeoutCount = 0,
    this.failToConnectCount = 0,
    this.reconnectCount = 0,
    this.maxReconnectDurationMs = 0,
    this.reconnectionCountTotal = 0,
    this.failToConnectCountTotal = 0,
    this.bleHistorySaturated = false,
    this.nativeBackgroundBytesConsumed = 0,
    this.nativeBackgroundPacketsConsumed = 0,
    this.diagnosticsDeviceId,
  });

  final int bleBytesReceived;
  final int websocketBytesSent;
  final String recordingState;
  final bool deviceConnected;
  final String deviceType;
  final bool batchModeEnabled;
  final bool foregroundTaskRunning;
  final int backgroundDisconnectCount;
  final int connectionTimeoutCount;
  final int failToConnectCount;
  final int reconnectCount;
  final int maxReconnectDurationMs;
  final int reconnectionCountTotal;
  final int failToConnectCountTotal;
  final bool bleHistorySaturated;
  final int nativeBackgroundBytesConsumed;
  final int nativeBackgroundPacketsConsumed;

  /// Used only to query the same device at resume; never emitted to analytics.
  final String? diagnosticsDeviceId;
}

/// Emits one privacy-safe summary when a real background session ends.
///
/// Audio, transcript content, device identifiers, and exact locations are
/// intentionally excluded. Analytics failures never affect lifecycle work.
class BackgroundResourceTelemetry {
  BackgroundResourceTelemetry({
    required BackgroundResourceEventEmitter emit,
    DateTime Function()? now,
    String Function()? sessionIdFactory,
    this.minimumDuration = const Duration(minutes: 1),
  })  : _emit = emit,
        _now = now ?? DateTime.now,
        _sessionIdFactory = sessionIdFactory ?? (() => DateTime.now().microsecondsSinceEpoch.toString());

  static const eventName = 'Mobile Background Resource Session';

  final BackgroundResourceEventEmitter _emit;
  final DateTime Function() _now;
  final String Function() _sessionIdFactory;
  final Duration minimumDuration;

  _BackgroundSessionStart? _activeSession;

  void onPaused(BackgroundResourceSnapshot snapshot) {
    if (_activeSession != null) return;
    _activeSession = _BackgroundSessionStart(
      id: _sessionIdFactory(),
      startedAt: _now(),
      snapshot: snapshot,
    );
  }

  Future<void> onResumed(BackgroundResourceSnapshotLoader loadSnapshot) async {
    final session = _activeSession;
    _activeSession = null;
    if (session == null) return;

    final endedAt = _now();
    final duration = endedAt.difference(session.startedAt);
    if (duration < minimumDuration) return;

    try {
      final end = await loadSnapshot(session.startedAt, session.snapshot);
      final durationSeconds = math.max(1, duration.inSeconds);
      final bleBytes = math.max(0, end.bleBytesReceived - session.snapshot.bleBytesReceived);
      final websocketBytes = math.max(0, end.websocketBytesSent - session.snapshot.websocketBytesSent);

      _emit(eventName, {
        'background_session_id': session.id,
        'background_duration_seconds': durationSeconds,
        'start_recording_state': session.snapshot.recordingState,
        'end_recording_state': end.recordingState,
        'start_device_connected': session.snapshot.deviceConnected,
        'end_device_connected': end.deviceConnected,
        'start_device_type': session.snapshot.deviceType,
        'end_device_type': end.deviceType,
        'batch_mode_enabled': end.batchModeEnabled,
        'ble_bytes_received': bleBytes,
        'websocket_bytes_sent': websocketBytes,
        'ble_receive_bytes_per_second': bleBytes ~/ durationSeconds,
        'websocket_send_bytes_per_second': websocketBytes ~/ durationSeconds,
        'foreground_task_running_on_resume': end.foregroundTaskRunning,
        'background_disconnect_count': end.backgroundDisconnectCount,
        'connection_timeout_count': end.connectionTimeoutCount,
        'fail_to_connect_count': end.failToConnectCount,
        'reconnect_count': end.reconnectCount,
        'max_reconnect_duration_ms': end.maxReconnectDurationMs,
        'reconnection_count_total': end.reconnectionCountTotal,
        'fail_to_connect_count_total': end.failToConnectCountTotal,
        'ble_history_saturated': end.bleHistorySaturated,
        'native_background_bytes_consumed': end.nativeBackgroundBytesConsumed,
        'native_background_packets_consumed': end.nativeBackgroundPacketsConsumed,
      });
    } catch (_) {
      // Telemetry is strictly fail-open. The app resume path must continue.
    }
  }
}

class _BackgroundSessionStart {
  const _BackgroundSessionStart({required this.id, required this.startedAt, required this.snapshot});

  final String id;
  final DateTime startedAt;
  final BackgroundResourceSnapshot snapshot;
}
