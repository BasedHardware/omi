import 'dart:math' as math;
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/utils/build_provenance.dart';

typedef BackgroundResourceEventEmitter = void Function(String eventName, Map<String, dynamic> properties);
typedef BackgroundResourceSnapshotLoader = Future<BackgroundResourceSnapshot> Function(
  DateTime backgroundStartedAt,
  BackgroundResourceSnapshot startSnapshot,
);

abstract interface class BackgroundCheckpointStore {
  Future<Map<String, Object>?> read();
  Future<void> write(Map<String, Object> checkpoint);
  Future<void> clear();
}

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

/// Wire values for `launch_context` on Mobile Background Observation Interrupted.
const backgroundInterruptLaunchColdStart = 'cold_start';
const backgroundInterruptLaunchResume = 'resume';
const backgroundInterruptLaunchRestored = 'restored';

const _knownBackgroundInterruptLaunchContexts = {
  backgroundInterruptLaunchColdStart,
  backgroundInterruptLaunchResume,
  backgroundInterruptLaunchRestored,
};

/// Best-effort relaunch label for an interrupted background observation.
///
/// [processAlreadyObserved] is true once this isolate has already created Home.
/// [osStateRestored] is true only when a Dart-visible signal says the OS restored
/// UI state. iOS `UIApplication.launchOptions` and UIKit restoration are not
/// forwarded by any existing pigeon or platform channel, and the app does not
/// enable Flutter restoration, so production leaves [osStateRestored] null.
/// Unknown inputs return null and the event omits `launch_context`.
String? classifyBackgroundInterruptLaunch({required bool? processAlreadyObserved, bool? osStateRestored}) {
  if (osStateRestored == true) return backgroundInterruptLaunchRestored;
  if (processAlreadyObserved == null) return null;
  return processAlreadyObserved ? backgroundInterruptLaunchResume : backgroundInterruptLaunchColdStart;
}

/// Drops unrecognized launch labels so recovery never invents a reason.
String? normalizeBackgroundInterruptLaunchContext(String? raw) {
  if (raw == null || !_knownBackgroundInterruptLaunchContexts.contains(raw)) return null;
  return raw;
}

/// Process-lifetime Home creation flag. Statics die with the isolate, so the
/// first Home in a process is a cold start and a later Home is a same-process
/// replacement.
class BackgroundInterruptProcessLaunch {
  static bool _observed = false;

  /// Whether Home was already created in this process. Records that it now has been.
  static bool markObserved() {
    final already = _observed;
    _observed = true;
    return already;
  }

  @visibleForTesting
  static void resetForTesting() {
    _observed = false;
  }
}

String? _provenanceGitSha() => BuildProvenance.fromEnvironment().gitSha;

/// Real build/sha only. `unknown` and blanks are the super-property sentinels
/// for a missing PackageInfo or dart-define, not an originating build.
String? _usableObservationIdentity(Object? raw) {
  if (raw is! String) return null;
  final value = raw.trim();
  if (value.isEmpty || value == 'unknown') return null;
  return value;
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
    this.checkpointStore,
    String Function()? ownerKey,
    int Function()? identityEpoch,
    bool Function()? enabled,
    String? Function()? currentBuild,
    String? Function()? currentGitSha,
  })  : _ownerKey = ownerKey ?? (() => 'anonymous'),
        _identityEpoch = identityEpoch ?? (() => 0),
        _enabled = enabled ?? (() => true),
        _currentBuild = currentBuild ?? (() => null),
        _currentGitSha = currentGitSha ?? _provenanceGitSha,
        _emit = emit,
        _now = now ?? DateTime.now,
        _sessionIdFactory = sessionIdFactory ?? (() => DateTime.now().microsecondsSinceEpoch.toString());

  static const eventName = 'Mobile Background Resource Session';

  final BackgroundResourceEventEmitter _emit;
  final DateTime Function() _now;
  final String Function() _sessionIdFactory;
  final Duration minimumDuration;
  final BackgroundCheckpointStore? checkpointStore;
  final String Function() _ownerKey;
  final int Function() _identityEpoch;
  final bool Function() _enabled;
  final String? Function() _currentBuild;
  final String? Function() _currentGitSha;
  Future<void> _storage = Future<void>.value();

  /// Completes after queued checkpoint writes and clears finish.
  @visibleForTesting
  Future<void> get pendingCheckpointWrites => _storage;

  Future<void> _serialize(Future<void> Function() operation) {
    _storage = _storage.then((_) => operation()).catchError((Object _) {});
    return _storage;
  }

  /// A previous process never observed a terminal background state. We know
  /// the observation was interrupted, not whether capture or the OS failed.
  ///
  /// [launchContext] is best-effort (`cold_start`, `resume`, `restored`).
  /// Null or unrecognized values are omitted.
  Future<void> recoverInterrupted({String? launchContext}) => _serialize(() async {
        final store = checkpointStore;
        if (store == null) return;
        final epoch = _identityEpoch();
        final owner = _ownerKey();
        final checkpoint = await store.read();
        if (checkpoint == null) return;
        await store.clear();
        if (!_enabled() || epoch != _identityEpoch() || owner != _ownerKey() || checkpoint['owner'] != owner) return;
        final started = DateTime.tryParse(checkpoint['started_at'] as String? ?? '');
        final id = checkpoint['background_session_id'];
        if (started == null || id is! String || _now().isBefore(started)) return;
        _emit('Mobile Background Observation Interrupted', {
          'background_session_id': id,
          'background_duration_seconds': _now().difference(started).inSeconds,
          'observation_state': 'unobserved',
          'start_recording_state': checkpoint['recording_state'] ?? 'unknown',
          'batch_mode_enabled': checkpoint['batch_mode_enabled'] == true,
          ..._originProperties(checkpoint),
          ..._launchProperties(launchContext),
        });
      });

  Map<String, dynamic> _originProperties(Map<String, Object> checkpoint) {
    final properties = <String, dynamic>{};
    final originBuild = _usableObservationIdentity(checkpoint['origin_build']);
    if (originBuild != null) {
      properties['interrupt_origin_build'] = originBuild;
      final current = _usableObservationIdentity(_readBuild());
      if (current != null) properties['interrupted_after_upgrade'] = originBuild != current;
    }
    final originSha = _usableObservationIdentity(checkpoint['origin_git_sha']);
    if (originSha != null) properties['interrupt_origin_git_sha'] = originSha;
    return properties;
  }

  Map<String, dynamic> _launchProperties(String? launchContext) {
    final normalized = normalizeBackgroundInterruptLaunchContext(launchContext);
    if (normalized == null) return const {};
    return {'launch_context': normalized};
  }

  String? _readBuild() {
    try {
      return _currentBuild();
    } catch (_) {
      return null;
    }
  }

  String? _readGitSha() {
    try {
      return _currentGitSha();
    } catch (_) {
      return null;
    }
  }

  _BackgroundSessionStart? _activeSession;

  void onPaused(BackgroundResourceSnapshot snapshot) {
    if (!_enabled()) return;
    if (_activeSession != null) return;
    _activeSession = _BackgroundSessionStart(
      id: _sessionIdFactory(),
      startedAt: _now(),
      snapshot: snapshot,
      owner: _ownerKey(),
      epoch: _identityEpoch(),
    );
    final session = _activeSession!;
    unawaited(_serialize(() async {
      if (!_enabled() || session.epoch != _identityEpoch() || session.owner != _ownerKey()) return;
      final checkpoint = <String, Object>{
        'owner': session.owner,
        'background_session_id': session.id,
        'started_at': session.startedAt.toUtc().toIso8601String(),
        'recording_state': session.snapshot.recordingState,
        'batch_mode_enabled': session.snapshot.batchModeEnabled,
      };
      final originBuild = _usableObservationIdentity(_readBuild());
      if (originBuild != null) checkpoint['origin_build'] = originBuild;
      final originSha = _usableObservationIdentity(_readGitSha());
      if (originSha != null) checkpoint['origin_git_sha'] = originSha;
      await checkpointStore?.write(checkpoint);
      if (!_enabled() || session.epoch != _identityEpoch() || session.owner != _ownerKey()) {
        await checkpointStore?.clear();
      }
    }));
  }

  Future<void> onResumed(BackgroundResourceSnapshotLoader loadSnapshot) async {
    final session = _activeSession;
    _activeSession = null;
    if (session == null) return;
    await _serialize(() async {
      await checkpointStore?.clear();
    });
    if (!_enabled() || session.epoch != _identityEpoch() || session.owner != _ownerKey()) return;

    final endedAt = _now();
    final duration = endedAt.difference(session.startedAt);
    if (duration < minimumDuration) return;

    try {
      final end = await loadSnapshot(session.startedAt, session.snapshot);
      if (!_enabled() || session.epoch != _identityEpoch() || session.owner != _ownerKey()) return;
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
  const _BackgroundSessionStart(
      {required this.id, required this.startedAt, required this.snapshot, required this.owner, required this.epoch});

  final String owner;
  final int epoch;

  final String id;
  final DateTime startedAt;
  final BackgroundResourceSnapshot snapshot;
}
