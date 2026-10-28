import 'dart:async';

class ConnectionReadCancelled implements Exception {}

/// A caller-owned deadline that can release even a non-cooperative dependency.
/// The underlying SDK/HTTP operation may finish later; it cannot publish twice.
class ConnectionRead<T> {
  ConnectionRead(Future<T> Function() load, Duration deadline) {
    _done.future.ignore(); // Cancellation stays observable to awaiting owners.
    _timer = Timer(deadline, () => _fail(TimeoutException('Connection read timed out')));
    unawaited(
        Future.sync(load).then<void>(_complete, onError: (Object error, StackTrace stack) => _fail(error, stack)));
  }

  final _done = Completer<T>();
  Timer? _timer;
  Future<T> get future => _done.future;

  void cancel() => _fail(ConnectionReadCancelled());

  void _complete(T value) {
    if (_done.isCompleted) return;
    _timer?.cancel();
    _done.complete(value);
  }

  void _fail(Object error, [StackTrace? stack]) {
    if (_done.isCompleted) return;
    _timer?.cancel();
    _done.completeError(error, stack);
  }
}
