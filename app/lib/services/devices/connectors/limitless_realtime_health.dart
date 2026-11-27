// Owns the bounded Limitless realtime-audio retry for one admitted capture and BLE link.
// Every retry is fenced by that owner and rearmed by sustained decoded-frame progress.

import 'dart:async';

enum LimitlessRealtimeHealthOutcome { restored, exhausted, censored }

/// Watches decoded frames while an admitted Custom Live capture owns the link.
class LimitlessRealtimeHealth {
  static const int _maxReactivationAttemptsPerEpisode = 2;

  LimitlessRealtimeHealth({
    required this.window,
    required this.isCurrent,
    required this.reactivate,
    required this.report,
    this.reactivationTimeout = const Duration(seconds: 5),
    Duration Function()? elapsed,
  }) : _elapsed = elapsed ?? _monotonicClock() {
    _lastFrame = _elapsed();
    _timer = Timer(window, _check);
  }

  final Duration window;
  final bool Function() isCurrent;
  final Future<bool> Function() reactivate;
  final void Function(LimitlessRealtimeHealthOutcome) report;
  final Duration reactivationTimeout;
  final Duration Function() _elapsed;

  Timer? _timer;
  late Duration _lastFrame;
  Duration? _firstRecoveryFrame;
  Duration? _recoveryDeadline;
  bool _attempted = false;
  int _reactivationAttempts = 0;
  bool _reactivationInFlight = false;
  bool _closed = false;

  bool get isClosed => _closed;
  bool get isRecoveryExhausted => _attempted && _recoveryDeadline == null;

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
        _reactivationAttempts = 0;
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
        _reactivationAttempts = 0;
        _recoveryDeadline = now + window * 2;
      }
      _attemptReactivation();
      final recoveryDeadline = _recoveryDeadline;
      if (recoveryDeadline != null) _timer = Timer(recoveryDeadline - now, _check);
      return;
    }

    var next = quietAt;
    final recoveryDeadline = _recoveryDeadline;
    if (recoveryDeadline != null && recoveryDeadline < next) next = recoveryDeadline;
    _timer = Timer(next - now, _check);
  }

  void _attemptReactivation() {
    if (_closed ||
        !_attempted ||
        _reactivationInFlight ||
        _reactivationAttempts >= _maxReactivationAttemptsPerEpisode ||
        _recoveryDeadline == null) {
      return;
    }
    _reactivationAttempts++;
    _reactivationInFlight = true;
    unawaited(_reactivate());
  }

  Future<void> _reactivate() async {
    var wroteEnable = false;
    try {
      if (_closed || !isCurrent()) {
        close();
        return;
      }
      wroteEnable = await reactivate().timeout(reactivationTimeout);
    } catch (_) {
      // Failed or skipped writes share the episode's bounded retry budget.
    } finally {
      _reactivationInFlight = false;
    }
    if (_closed) return;
    if (!wroteEnable && _reactivationAttempts < _maxReactivationAttemptsPerEpisode) {
      final deadline = _recoveryDeadline;
      if (deadline != null) {
        _timer?.cancel();
        final remaining = deadline - _elapsed();
        if (remaining <= Duration.zero) {
          _check();
        } else {
          _timer = Timer(remaining < window ? remaining : window, _check);
        }
      }
    }
    if (!isCurrent()) close();
  }
}
