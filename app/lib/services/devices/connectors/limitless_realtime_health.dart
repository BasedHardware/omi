// Owns the bounded Limitless realtime-audio retry for one admitted capture and BLE link.
// Every retry is fenced by that owner and rearmed by sustained decoded-frame progress.

import 'dart:async';

enum LimitlessRealtimeHealthOutcome { restored, exhausted, censored }

/// Watches decoded frames while an admitted Custom Live capture owns the link.
class LimitlessRealtimeHealth {
  LimitlessRealtimeHealth({
    required this.window,
    required this.isCurrent,
    required this.reactivate,
    required this.report,
    Duration Function()? elapsed,
  }) : _elapsed = elapsed ?? _monotonicClock() {
    _lastFrame = _elapsed();
    _timer = Timer(window, _check);
  }

  final Duration window;
  final bool Function() isCurrent;
  final Future<void> Function() reactivate;
  final void Function(LimitlessRealtimeHealthOutcome) report;
  final Duration Function() _elapsed;

  Timer? _timer;
  late Duration _lastFrame;
  Duration? _firstRecoveryFrame;
  Duration? _recoveryDeadline;
  bool _attempted = false;
  bool _closed = false;

  bool get isClosed => _closed;

  static Duration Function() _monotonicClock() {
    final clock = Stopwatch()..start();
    return () => clock.elapsed;
  }

  void observeFrame() {
    if (_closed) return;
    final now = _elapsed();
    if (_attempted) {
      if (_firstRecoveryFrame == null || now - _lastFrame >= window) _firstRecoveryFrame = now;
      final deadline = _recoveryDeadline;
      if (now - _firstRecoveryFrame! >= window && (deadline == null || now < deadline)) {
        if (!isCurrent()) {
          close();
          return;
        }
        _firstRecoveryFrame = null;
        _attempted = false;
        _recoveryDeadline = null;
        if (deadline != null) report(LimitlessRealtimeHealthOutcome.restored);
      }
    }
    _lastFrame = now;
    _timer ??= Timer(window, _check);
  }

  void close() {
    if (_closed) return;
    _closed = true;
    _timer?.cancel();
    _timer = null;
    if (_recoveryDeadline != null) report(LimitlessRealtimeHealthOutcome.censored);
  }

  void _check() {
    _timer = null;
    if (_closed || !isCurrent()) {
      close();
      return;
    }
    final now = _elapsed();
    final quietAt = _lastFrame + window;
    final deadline = _recoveryDeadline;
    if (deadline != null && now >= deadline) {
      _recoveryDeadline = null;
      report(LimitlessRealtimeHealthOutcome.exhausted);
    }

    if (now >= quietAt) {
      _firstRecoveryFrame = null;
      if (!_attempted) {
        _attempted = true;
        _recoveryDeadline = now + window * 2;
        unawaited(_reactivate());
      }
      final recoveryDeadline = _recoveryDeadline;
      if (recoveryDeadline != null) _timer = Timer(recoveryDeadline - now, _check);
      return;
    }

    var next = quietAt;
    final recoveryDeadline = _recoveryDeadline;
    if (recoveryDeadline != null && recoveryDeadline < next) next = recoveryDeadline;
    _timer = Timer(next - now, _check);
  }

  Future<void> _reactivate() async {
    if (_closed || !isCurrent()) {
      close();
      return;
    }
    try {
      await reactivate();
    } catch (_) {
      // The same terminal deadline covers write failures and missing frames.
    }
    if (!isCurrent()) close();
  }
}
