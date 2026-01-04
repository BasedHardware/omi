import 'dart:async';

class Mutex {
  Future<void>? _lastLock;

  /// Acquires the mutex. Returns a future that completes when the lock is held.
  /// The caller MUST call [release] when done with the critical section.
  Future<void> acquire() async {
    // Atomically capture the current lock and install our own.
    final previousLock = _lastLock;
    final completer = Completer<void>();
    _lastLock = completer.future;

    // Wait for the previous holder to release.
    if (previousLock != null) {
      try {
        await previousLock;
      } catch (_) {}
    }

    // Now we hold the lock. Store completer so release() can complete it.
    _currentCompleter = completer;
  }

  Completer<void>? _currentCompleter;

  /// Releases the mutex, allowing the next waiter to proceed.
  void release() {
    final completer = _currentCompleter;
    _currentCompleter = null;
    if (completer != null && !completer.isCompleted) {
      completer.complete();
    }
  }
}
