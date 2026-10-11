import 'dart:async';

/// Preserves both failures when an unsuccessful capture also fails to stop.
/// Callers must log types only: exception text can contain private data.
class PhysicalCaptureCleanupFailure implements Exception {
  PhysicalCaptureCleanupFailure(this.captureError, this.cleanupError);

  final Object? captureError;
  final Object cleanupError;
}

/// Owns a single capture attempt, including partial starts and mode rejection.
/// Reporting must succeed within the recording window, but never extends it.
Future<void> runBoundedPhysicalCapture({
  required Duration duration,
  required Future<void> Function() start,
  required Future<void> Function() reportStarted,
  required Future<void> Function() stop,
}) async {
  Timer? deadline;
  Object? captureError;
  try {
    await start();
    final finished = Completer<void>();
    var reported = false;
    deadline = Timer(duration, () {
      if (finished.isCompleted) return;
      if (reported) {
        finished.complete();
      } else {
        finished.completeError(TimeoutException('Capture reporting exceeded the recording window.'));
      }
    });
    // Attach an error handler immediately, including for a late response after
    // the deadline. A stalled or failed collector cannot strand the recorder.
    unawaited(Future<void>.sync(reportStarted).then((_) {
      reported = true;
    }, onError: (Object error, StackTrace stack) {
      if (!finished.isCompleted) finished.completeError(error, stack);
    }));
    await finished.future;
  } catch (error) {
    captureError = error;
    rethrow;
  } finally {
    deadline?.cancel();
    try {
      await stop();
    } catch (error, stack) {
      Error.throwWithStackTrace(PhysicalCaptureCleanupFailure(captureError, error), stack);
    }
  }
}
