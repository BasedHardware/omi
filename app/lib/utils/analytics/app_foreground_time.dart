import 'package:flutter/widgets.dart';

import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';

/// Measures how long the app is in front, and how much of that with capture active.
///
/// "In front" is the lifecycle state `resumed` and nothing else. A launch in the background has no
/// lifecycle state at all and counts as not in front (the listening connection's own report treats
/// that as foreground, which is why its iOS numbers cannot be used). `inactive` (the notification
/// shade, a system dialog, the app switcher) stops the clock without ending the stretch.
///
/// One event, `App Foreground Ended`, is sent each time the app really leaves the front (`paused`,
/// `hidden` or `detached`) after at least a second in front, with two whole numbers of seconds. Sum
/// them per person and day for daily time in the app. Nothing is stored on the phone: a stretch is
/// lost only when the app dies while in front without a lifecycle change.
class AppForegroundTime {
  AppForegroundTime({
    required bool Function() capturing,
    DateTime Function()? now,
    void Function(RegisteredEvent event)? emit,
  })  : _capturing = capturing,
        _now = now ?? DateTime.now,
        _emit = emit ?? const TypedEvents().emit;

  /// Capture is active: a pendant streaming or the phone recording, and not paused.
  final bool Function() _capturing;
  final DateTime Function() _now;
  final void Function(RegisteredEvent event) _emit;

  /// One stretch never reports more than this, whatever the phone's clock did meanwhile.
  static const maxStretch = Duration(hours: 12);

  DateTime? _frontSince;
  DateTime? _capturingSince;
  Duration _front = Duration.zero;
  Duration _capturingFront = Duration.zero;

  bool get inFront => _frontSince != null;

  /// Call once with the lifecycle state at start-up (null when the app was launched in the background).
  void start(AppLifecycleState? initial) {
    if (initial != null) onLifecycle(initial);
  }

  void onLifecycle(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        if (_frontSince != null) return;
        final now = _now();
        _frontSince = now;
        if (_capturing()) _capturingSince = now;
      case AppLifecycleState.inactive:
        _stopClocks();
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
      case AppLifecycleState.detached:
        _stopClocks();
        _report();
    }
  }

  /// Capture started, stopped, paused or resumed. Cheap; call on every capture change.
  void onCaptureChanged() {
    final since = _frontSince;
    if (since == null) return;
    final capturing = _capturing();
    if (capturing && _capturingSince == null) {
      _capturingSince = _now();
    } else if (!capturing && _capturingSince != null) {
      _capturingFront += _elapsed(_capturingSince!);
      _capturingSince = null;
    }
  }

  void _stopClocks() {
    final since = _frontSince;
    if (since == null) return;
    _front += _elapsed(since);
    _frontSince = null;
    if (_capturingSince case final capturingSince?) {
      _capturingFront += _elapsed(capturingSince);
      _capturingSince = null;
    }
  }

  // A clock set backwards while in front must not produce a negative time.
  Duration _elapsed(DateTime since) {
    final elapsed = _now().difference(since);
    return elapsed.isNegative ? Duration.zero : elapsed;
  }

  void _report() {
    var front = _front, capturing = _capturingFront;
    _front = Duration.zero;
    _capturingFront = Duration.zero;
    if (front > maxStretch) front = maxStretch;
    if (capturing > front) capturing = front;
    if (front.inSeconds < 1) return;
    _emit(AppForegroundEnded(foregroundSeconds: front.inSeconds, capturingSeconds: capturing.inSeconds));
  }
}
