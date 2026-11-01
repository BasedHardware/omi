import 'connection_read.dart';
import 'dart:async';

enum ConnectionProbe { pending, connected, failed }

enum ConnectionWaitOutcome { connected, failed, timedOut, cancelled }

/// One authorization attempt owns one bounded, non-overlapping probe loop.
/// Persistent connection state remains in the provider/page that supplies [probe].
class ConnectionWait {
  ConnectionWait({
    required this.probe,
    required this.isCurrent,
    this.interval = const Duration(seconds: 3),
    this.probeTimeout = const Duration(seconds: 20),
    this.waitTimeout = const Duration(minutes: 5),
  });

  final Future<ConnectionProbe> Function() probe;
  final bool Function() isCurrent;
  final Duration interval;
  final Duration probeTimeout;
  final Duration waitTimeout;
  final _done = Completer<ConnectionWaitOutcome>();
  Timer? _next;
  Timer? _deadline;
  ConnectionRead<ConnectionProbe>? _probeRead;
  bool _started = false;
  bool _checking = false;
  bool _refreshQueued = false;

  bool get isActive => _started && !_done.isCompleted;

  Future<ConnectionWaitOutcome> start() {
    if (!_started && !_done.isCompleted) {
      _started = true;
      _deadline = Timer(waitTimeout, () => _finish(ConnectionWaitOutcome.timedOut));
      unawaited(_check());
    }
    return _done.future;
  }

  /// Foreground return requests a fresh probe without overlapping a slow read.
  void refresh() {
    if (!isActive) return;
    _next?.cancel();
    if (_checking) {
      _refreshQueued = true;
    } else {
      unawaited(_check());
    }
  }

  void cancel() => _finish(ConnectionWaitOutcome.cancelled);

  void _finish(ConnectionWaitOutcome outcome) {
    if (_done.isCompleted) return;
    _next?.cancel();
    _deadline?.cancel();
    _probeRead?.cancel();
    _done.complete(outcome);
  }

  Future<void> _check() async {
    if (!isActive || _checking) return;
    if (!isCurrent()) {
      cancel();
      return;
    }
    _checking = true;
    final read = ConnectionRead(probe, probeTimeout);
    _probeRead = read;
    ConnectionProbe result;
    try {
      result = await read.future;
    } catch (_) {
      result = ConnectionProbe.failed;
    }
    _probeRead = null;
    _checking = false;
    if (!isActive) return;
    if (!isCurrent()) {
      cancel();
      return;
    }
    if (_refreshQueued) {
      _refreshQueued = false;
      unawaited(_check());
      return;
    }
    switch (result) {
      case ConnectionProbe.connected:
        _finish(ConnectionWaitOutcome.connected);
      case ConnectionProbe.failed:
        _finish(ConnectionWaitOutcome.failed);
      case ConnectionProbe.pending:
        _next = Timer(interval, () => unawaited(_check()));
    }
  }
}
