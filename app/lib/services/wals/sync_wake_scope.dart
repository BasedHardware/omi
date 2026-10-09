import 'dart:async';

/// Process-local admission fence for an OS-granted backlog pass. BLE links and
/// storage remain available, but no callback may start a live listen session.
class SyncWakeScope {
  static int _depth = 0;
  static Completer<void>? _idle;
  static Future<void> get whenIdle => _idle?.future ?? Future.value();
  static bool get syncOnly => _depth > 0;

  static Future<T> run<T>(Future<T> Function() drain) async {
    if (_depth++ == 0) _idle = Completer<void>();
    try {
      return await drain();
    } finally {
      if (--_depth == 0) {
        final idle = _idle;
        _idle = null;
        idle?.complete();
      }
    }
  }
}
