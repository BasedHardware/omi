enum MetaCaptureHealth { streaming, paused, stopped, stale }

enum MetaCaptureWatchdogAction { wait, restart }

class MetaCaptureWatchdog {
  int _attempts = 0;

  MetaCaptureWatchdogAction nextAction(MetaCaptureHealth health) {
    switch (health) {
      case MetaCaptureHealth.streaming:
      case MetaCaptureHealth.paused:
        return MetaCaptureWatchdogAction.wait;
      case MetaCaptureHealth.stopped:
      case MetaCaptureHealth.stale:
        return MetaCaptureWatchdogAction.restart;
    }
  }

  Duration nextDelay(MetaCaptureHealth health) {
    if (nextAction(health) == MetaCaptureWatchdogAction.wait) return Duration.zero;
    final seconds = 1 << _attempts.clamp(0, 5);
    return Duration(seconds: seconds);
  }

  void recordRestartAttempt() {
    _attempts += 1;
  }

  void recordHealthyFrame() {
    _attempts = 0;
  }

  /// Clears restart backoff. Call when a new capture session starts so a
  /// previous session's failed restarts don't penalize the fresh session.
  void reset() {
    _attempts = 0;
  }
}
