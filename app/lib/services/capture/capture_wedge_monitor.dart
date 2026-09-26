import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/capture/capture_composition.dart';
import 'package:omi/services/capture/conversation_source_for_device.dart';
import 'package:omi/utils/logger.dart';

const String captureRecoveryFeatureFlag = 'mobile-capture-recovery-v1';

class CaptureWedgeEpisode {
  CaptureWedgeEpisode({
    required this.deviceId,
    required this.source,
    required this.trigger,
    required this.declaredAt,
  });

  final String deviceId;
  final String source;
  final String trigger;
  final DateTime declaredAt;

  bool retryAttempted = false;
  bool promptVisible = false;
  bool promptShownEmitted = false;
}

typedef CaptureWedgeTrack = void Function(String event, Map<String, Object> properties);

class CaptureWedgeMonitor extends ChangeNotifier {
  CaptureWedgeMonitor({
    DateTime Function()? now,
    required Future<bool> Function() featureGate,
    required CaptureWedgeTrack track,
    required Future<void> Function(String deviceId) bleRetry,
    required String Function() appBuild,
    required String Function() platform,
  })  : _now = now ?? DateTime.now,
        _featureGate = featureGate,
        _track = track,
        _bleRetry = bleRetry,
        _appBuild = appBuild,
        _platform = platform;

  static CaptureWedgeMonitor? _instance;
  static CaptureWedgeMonitor get instance => _instance ??= composeCaptureWedgeMonitor();
  static set instance(CaptureWedgeMonitor monitor) => _instance = monitor;

  static const Duration zeroByteWindow = Duration(minutes: 10);
  static const int zeroByteThreshold = 3;
  static const Duration rapidDropWindow = Duration(minutes: 5);
  static const Duration rapidDropMaxDuration = Duration(seconds: 15);
  static const int rapidDropThreshold = 3;
  static const Duration resolveWindow = Duration(minutes: 30);
  static const Duration retryTimeout = Duration(seconds: 10);

  static const String triggerZeroByteStreak = 'zero_byte_streak';
  static const String triggerRapidReconnects = 'rapid_reconnects';

  final DateTime Function() _now;
  final Future<bool> Function() _featureGate;
  final CaptureWedgeTrack _track;
  final Future<void> Function(String deviceId) _bleRetry;
  final String Function() _appBuild;
  final String Function() _platform;

  final Map<String, _DeviceWedgeState> _devices = {};
  final Map<int, ({String deviceId, String source})> _openSessions = {};
  final Set<String> _retryInFlightDevices = {};
  int _nextSessionHandle = 0;

  static bool isCaptureSourceInScope(String? source) => source == 'omi' || source == 'friend_com';

  _DeviceWedgeState _stateFor(String deviceId) => _devices.putIfAbsent(deviceId, _DeviceWedgeState.new);

  int onCaptureSessionConnected({required String deviceId, required String source}) {
    if (!isCaptureSourceInScope(source)) return -1;
    final handle = ++_nextSessionHandle;
    _openSessions[handle] = (deviceId: deviceId, source: source);
    return handle;
  }

  void onCaptureSessionEnded(
    int handle, {
    required int binaryBytesSent,
    bool intentional = false,
  }) {
    final session = _openSessions.remove(handle);
    if (session == null) return;
    final state = _stateFor(session.deviceId);
    if (binaryBytesSent > 0) {
      state.zeroByteSessionEnds.clear();
      _resolveIfActive(session.deviceId, state);
      return;
    }
    if (intentional) return;
    final now = _now();
    final ends = state.zeroByteSessionEnds;
    ends.add(now);
    ends.removeWhere((t) => now.difference(t) > zeroByteWindow);
    if (ends.length >= zeroByteThreshold &&
        ends.last.difference(ends[ends.length - zeroByteThreshold]) <= zeroByteWindow) {
      unawaited(_maybeDeclare(
        state,
        deviceId: session.deviceId,
        source: session.source,
        trigger: triggerZeroByteStreak,
      ));
    }
  }

  void onBleSessionEnded({
    required String deviceId,
    required DeviceType deviceType,
    required Duration duration,
    bool intentional = false,
  }) {
    final source = conversationSourceForDeviceType(deviceType);
    if (!isCaptureSourceInScope(source)) return;
    if (_retryInFlightDevices.contains(deviceId)) return;
    final state = _stateFor(deviceId);
    if (intentional) {
      state.rapidDropEnds.clear();
      if (state.episode != null) {
        state.episode = null;
        notifyListeners();
      }
      return;
    }
    if (duration >= rapidDropMaxDuration) return;
    final now = _now();
    final drops = state.rapidDropEnds;
    drops.add(now);
    drops.removeWhere((t) => now.difference(t) > rapidDropWindow);
    if (drops.length >= rapidDropThreshold) {
      unawaited(_maybeDeclare(
        state,
        deviceId: deviceId,
        source: source!,
        trigger: triggerRapidReconnects,
      ));
    }
  }

  CaptureWedgeEpisode? get visiblePrompt {
    for (final state in _devices.values) {
      final episode = state.episode;
      if (episode != null && episode.promptVisible) return episode;
    }
    return null;
  }

  bool get promptVisible => visiblePrompt != null;

  void markPromptShown() {
    final episode = visiblePrompt;
    if (episode == null || episode.promptShownEmitted) return;
    episode.promptShownEmitted = true;
    _safeTrack('Capture Recovery Prompt Shown', {'source': episode.source, 'trigger': episode.trigger});
  }

  void onRecoveryActioned({required String surface}) {
    _safeTrack('Capture Recovery Actioned', {'surface': surface});
  }

  void dismissDeviceEpisode(String deviceId) {
    final state = _devices[deviceId];
    if (state == null) return;
    state.rapidDropEnds.clear();
    if (state.episode == null) return;
    state.episode = null;
    notifyListeners();
  }

  void reset() {
    _devices.clear();
    _openSessions.clear();
    _retryInFlightDevices.clear();
    notifyListeners();
  }

  @override
  void dispose() {
    _devices.clear();
    _openSessions.clear();
    _retryInFlightDevices.clear();
    super.dispose();
  }

  Future<void> _maybeDeclare(
    _DeviceWedgeState state, {
    required String deviceId,
    required String source,
    required String trigger,
  }) async {
    if (state.episode != null) return;
    bool allowed;
    try {
      allowed = await _featureGate();
    } catch (_) {
      allowed = false;
    }
    if (!allowed || state.episode != null) return;
    final episode = CaptureWedgeEpisode(deviceId: deviceId, source: source, trigger: trigger, declaredAt: _now());
    state.episode = episode;
    _safeTrack('Capture Wedge Detected', {
      'source': source,
      'consecutive_zero_byte_sessions': state.zeroByteSessionEnds.length,
      'trigger': trigger,
      'app_build': _appBuild(),
      'platform': _platform(),
    });
    notifyListeners();
    unawaited(_attemptRecovery(episode));
  }

  Future<void> _attemptRecovery(CaptureWedgeEpisode episode) async {
    episode.retryAttempted = true;
    _retryInFlightDevices.add(episode.deviceId);
    try {
      await _bleRetry(episode.deviceId).timeout(retryTimeout);
    } catch (e) {
      Logger.debug('CaptureWedgeMonitor: BLE retry for ${episode.deviceId} failed: $e');
    } finally {
      _retryInFlightDevices.remove(episode.deviceId);
    }
    if (_episodeFor(episode.deviceId) != episode) return;
    episode.promptVisible = true;
    notifyListeners();
  }

  bool hasActiveEpisode(String deviceId) => _devices[deviceId]?.episode != null;

  CaptureWedgeEpisode? _episodeFor(String deviceId) => _devices[deviceId]?.episode;

  void _resolveIfActive(String deviceId, _DeviceWedgeState state) {
    final episode = state.episode;
    if (episode == null) return;
    if (_now().difference(episode.declaredAt) <= resolveWindow) {
      _safeTrack('Capture Recovery Resolved', {'source': episode.source, 'trigger': episode.trigger});
    }
    state.episode = null;
    notifyListeners();
  }

  void _safeTrack(String event, Map<String, Object> properties) {
    try {
      _track(event, properties);
    } catch (e) {
      Logger.debug('CaptureWedgeMonitor: track failed for $event: $e');
    }
  }
}

class _DeviceWedgeState {
  final List<DateTime> zeroByteSessionEnds = [];
  final List<DateTime> rapidDropEnds = [];
  CaptureWedgeEpisode? episode;
}
