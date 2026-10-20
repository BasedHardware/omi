import 'package:flutter/foundation.dart';

import 'package:omi/services/capture/capture_composition.dart';
import 'package:omi/services/telemetry/client_telemetry.dart';
import 'package:omi/utils/logger.dart';
import 'package:uuid/uuid.dart';

/// What capture looks like at one check. Built by the controller every
/// [CaptureContinuityMonitor.checkInterval].
@immutable
class CaptureContinuityProbe {
  const CaptureContinuityProbe({
    required this.deviceId,
    required this.source,
    required this.captureExpected,
    required this.capturing,
    required this.phase,
    required this.syncFenced,
  });

  /// The connected pendant, or null when none is connected.
  final String? deviceId;

  /// Conversation source for the pendant type (`omi`, `openglass`).
  final String source;

  /// Capture should be on: not muted or paused, not Transcribe Later, not
  /// stopped by a caller (voice profile), and no phone recording or call owns it.
  final bool captureExpected;

  /// Capture holds the pendant's audio subscription.
  final bool capturing;

  /// Capture phase name, for the event only.
  final String phase;

  /// An OS upload window (SyncWakeScope) is deferring capture starts.
  final bool syncFenced;
}

/// An open episode, for the dogfood banner.
@immutable
class CaptureContinuityAlert {
  const CaptureContinuityAlert({required this.deviceId, required this.since});

  final String deviceId;

  /// When frames last reached custody (or the condition began).
  final DateTime since;
}

/// Invariant monitor: a connected pendant whose audio reaches neither the live
/// socket nor the local WAL.
///
/// Builds 1.0.560-563 (#20837) skipped the pendant capture start whenever a
/// reconnect landed during an upload pass. Firmware 3.0.21 discards audio while
/// a phone is connected but not subscribed, so nothing was recorded anywhere,
/// and the existing wedge monitor never saw it: `connected_no_bytes` watches
/// open capture sessions, and there was none. About 640 users hit the bug for
/// a week before anyone noticed.
///
/// This monitor declares `Capture Wedge Detected` with trigger
/// `connected_not_capturing` when, for longer than [threshold]:
/// - a pendant is connected and capture is expected to be on;
/// - capture holds no pendant audio subscription; and
/// - no pendant frame reached custody (WAL or socket, including audio the
///   transport delivered with no listener and capture persisted).
///
/// The event is emitted in every build: it is the promotion gate's direct
/// signal. Debug and TestFlight builds also raise [dogfoodAlert], which Home
/// shows as a banner, so a dogfooder sees the bug in minutes. It never retries
/// or restarts anything itself: recovery belongs to the controller.
class CaptureContinuityMonitor {
  CaptureContinuityMonitor({
    required DateTime Function() now,
    required void Function(String event, Map<String, Object> properties) track,
    required bool Function() dogfood,
    required String Function() appBuild,
    required String Function() platform,
    this.threshold = defaultThreshold,
  })  : _now = now,
        _track = track,
        _dogfood = dogfood,
        _appBuild = appBuild,
        _platform = platform;

  static CaptureContinuityMonitor? _instance;
  static CaptureContinuityMonitor get instance => _instance ??= composeCaptureContinuityMonitor();
  static set instance(CaptureContinuityMonitor monitor) => _instance = monitor;

  static const Duration defaultThreshold = Duration(seconds: 60);
  static const Duration checkInterval = Duration(seconds: 15);
  static const String trigger = 'connected_not_capturing';

  final Duration threshold;
  final DateTime Function() _now;
  final void Function(String event, Map<String, Object> properties) _track;
  final bool Function() _dogfood;
  final String Function() _appBuild;
  final String Function() _platform;

  DateTime? _lastCustodyAt;
  DateTime? _conditionSince;
  DateTime? _declaredAt;
  String? _declaredSource;

  /// Non-null while an episode is open in a debug or TestFlight build.
  final ValueNotifier<CaptureContinuityAlert?> dogfoodAlert = ValueNotifier(null);

  /// A pendant frame reached the WAL or the socket.
  void onFrameInCustody() => _lastCustodyAt = _now();

  void observe(CaptureContinuityProbe probe) {
    final now = _now();
    final deviceId = probe.deviceId;
    if (deviceId == null || !probe.captureExpected || probe.capturing) {
      _conditionSince = null;
      _resolve(now);
      return;
    }
    final since = _conditionSince ??= now;
    final custody = _lastCustodyAt;
    final silentSince = custody != null && custody.isAfter(since) ? custody : since;
    if (now.difference(silentSince) < threshold || _declaredAt != null) return;
    _declaredAt = now;
    _declaredSource = probe.source;
    _safeTrack('Capture Wedge Detected', {
      'source': probe.source,
      'trigger': trigger,
      'app_build': _appBuild(),
      'platform': _platform(),
      'seconds_without_custody': now.difference(silentSince).inSeconds,
      'capture_phase': probe.phase,
      'sync_fenced': probe.syncFenced,
    });
    try {
      // The replacement collector, for when PostHog emission is retired.
      ClientTelemetry.instance.observeWedge(
        operationId: const Uuid().v4(),
        phase: 'detected',
        trigger: trigger,
        outcome: 'pending',
      );
    } catch (_) {}
    if (_dogfood()) dogfoodAlert.value = CaptureContinuityAlert(deviceId: deviceId, since: silentSince);
  }

  void _resolve(DateTime now) {
    final declaredAt = _declaredAt;
    if (declaredAt == null) return;
    _declaredAt = null;
    _safeTrack('Capture Recovery Resolved', {
      'source': _declaredSource ?? 'omi',
      'trigger': trigger,
      'seconds_to_resolve': now.difference(declaredAt).inSeconds,
    });
    dogfoodAlert.value = null;
  }

  void _safeTrack(String event, Map<String, Object> properties) {
    try {
      _track(event, properties);
    } catch (error) {
      Logger.debug('CaptureContinuityMonitor: track failed for $event: $error');
    }
  }
}
