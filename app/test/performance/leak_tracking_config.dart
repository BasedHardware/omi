/// Configuration for leak_tracker integration in performance tests.
///
/// leak_tracker detects memory leaks in Flutter apps by tracking
/// object allocation and disposal. This config ensures we catch
/// leaks in providers, streams, and controllers.
///
/// Usage in tests:
///   import 'leak_tracking_config.dart';
///   
///   void main() {{
///     configureLeakTracking();
///     // ... your tests
///   }}
///
/// See: https://pub.dev/packages/leak_tracker

// ignore: depend_on_referenced_packages
import 'package:leak_tracker/leak_tracker.dart';

void configureLeakTracking() {
  LeakTracking.start(
    const LeakTrackingConfiguration(
      stdoutLeaks: true,
      // Notify immediately when a leak is detected
      notifyDevTools: true,
      // Track these specific types (common leak sources in Flutter)
      leakDiagnosticConfig: LeakDiagnosticConfig(
        collectRetainingPathForNotGCed: true,
        collectStackTraceOnStart: true,
      ),
    ),
  );
}

void stopLeakTracking() {
  final leaks = LeakTracking.stop();
  if (leaks != null && leaks.total > 0) {
    throw StateError(
      'Memory leaks detected!\n'
      'Not disposed: \${leaks.notDisposed.length}\n'
      'Not GCed: \${leaks.notGCed.length}\n'
      'Details: \$leaks',
    );
  }
}
