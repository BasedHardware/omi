import 'dart:async';

import 'package:omi/services/capture/capture_seams.dart';

/// Bounded virtual time for deterministic capture-recovery replay.
///
/// One [VirtualClock] persists across process-death generations (it models
/// wall time); each generation gets a fresh [ManualScheduler] so timers from a
/// killed process can never fire in the reconstructed one.
class VirtualClock {
  DateTime _now;

  VirtualClock(this._now);

  DateTime now() => _now;

  void advanceTo(DateTime t) {
    assert(!t.isBefore(_now), 'virtual time must not move backwards: $_now -> $t');
    _now = t;
  }
}

/// A [Timer] whose firing is owned by a [ManualScheduler].
class FakeTimer implements Timer {
  final Duration? _interval;
  final Object? Function() _fire;
  final String label;
  bool _active = true;
  bool _done = false;
  DateTime _nextDeadline;
  int fires = 0;

  FakeTimer._(Duration delay, this._interval, this._fire, this.label, DateTime start)
      : _nextDeadline = start.add(delay);

  @override
  void cancel() => _active = false;

  @override
  bool get isActive => _active;

  @override
  int get tick => fires;

  bool get isPeriodic => _interval != null;

  DateTime get nextDeadline => _nextDeadline;
}

/// Manual timer scheduler: implements [CaptureScheduling] for
/// [CaptureController] and its `periodic` tear-off doubles as the WAL periodic
/// seam. Time advances only through [elapse], which fires due timers in
/// deadline order (stable by registration order for identical deadlines).
///
/// Bounded by construction: [elapse] refuses to advance past [maxTotalAdvance]
/// of cumulative virtual time or fire more than [maxFires] timer callbacks, so
/// a runaway periodic loop fails the scenario instead of hanging it.
class ManualScheduler implements CaptureScheduling {
  final VirtualClock clock;
  final Duration maxTotalAdvance;
  final int maxFires;

  final List<FakeTimer> _timers = [];
  final List<Future<void>> _inFlightIo = [];
  Duration _advanced = Duration.zero;
  int _fired = 0;

  ManualScheduler({required this.clock, this.maxTotalAdvance = const Duration(hours: 24), this.maxFires = 100000});

  @override
  Timer once(Duration delay, void Function() callback) =>
      _register(delay, null, () => _invoke(callback), 'once($delay)');

  @override
  Timer periodic(Duration interval, void Function(Timer timer) callback) {
    late final FakeTimer timer;
    timer = _register(interval, interval, () => _invoke(callback, timer), 'periodic($interval)');
    return timer;
  }

  FakeTimer _register(Duration delay, Duration? interval, Object? Function() fire, String label) {
    final t = FakeTimer._(delay, interval, fire, label, clock.now());
    _timers.add(t);
    return t;
  }

  /// Production WAL timers are declared `void Function(Timer)` but the bodies
  /// are `async` and return a discarded [Future] (`LocalWalSync._flush`).
  /// Invoke through [Function] so that Future is observable.
  static Object? _invoke(Function callback, [Timer? timer]) => timer == null ? callback() : callback(timer);

  List<FakeTimer> get pendingTimers => _timers.where((t) => t._active && !t._done).toList();

  bool get hasPendingTimers => pendingTimers.isNotEmpty;

  List<String> get pendingTimerLabels => pendingTimers.map((t) => t.label).toList()..sort();

  /// True while a Future returned by a fired callback has not yet completed.
  /// Coordinator-idle is a different signal and is not sufficient.
  bool get hasInFlightIo => _inFlightIo.isNotEmpty;

  /// Await every Future a fired callback returned, including Futures those
  /// completions start. Quiescence is observed — no wall-clock sleeps.
  Future<void> waitForCallbackIo() async {
    while (_inFlightIo.isNotEmpty) {
      final batch = List<Future<void>>.of(_inFlightIo);
      _inFlightIo.clear();
      await Future.wait(batch);
    }
  }

  void _trackCallbackResult(Object? result) {
    if (result is Future) {
      _inFlightIo.add(Future<void>.sync(() async {
        await result;
      }));
    }
  }

  /// Advances virtual time by [duration], firing every timer that comes due.
  /// Callbacks run synchronously; any [Future] they return is tracked until
  /// [waitForCallbackIo] (see [CaptureReplayWorld.settle]).
  void elapse(Duration duration) {
    final totalLimitCheck = _advanced + duration;
    if (totalLimitCheck > maxTotalAdvance) {
      throw StateError(
        'ManualScheduler exceeded bounded virtual time ($totalLimitCheck > $maxTotalAdvance); runaway timer loop?',
      );
    }
    final target = clock.now().add(duration);
    while (true) {
      // Earliest pending timer at or before the target — the boundary is
      // inclusive: elapse(5s) must fire a timer scheduled 5s out.
      FakeTimer? due;
      for (final t in _timers) {
        if (!t._active || t._done) continue;
        if (!t._nextDeadline.isAfter(target) && (due == null || t._nextDeadline.isBefore(due._nextDeadline))) {
          due = t;
        }
      }
      if (due == null) {
        _advanced = totalLimitCheck;
        clock.advanceTo(target);
        return;
      }
      final t = due;
      clock.advanceTo(t._nextDeadline);
      if (t._interval == null) {
        t._done = true;
        t._active = false;
      } else {
        t._nextDeadline = t._nextDeadline.add(t._interval!);
      }
      t.fires++;
      _fired++;
      if (_fired > maxFires) {
        throw StateError('ManualScheduler exceeded $maxFires timer fires; runaway periodic loop?');
      }
      _trackCallbackResult(t._fire());
    }
  }
}
