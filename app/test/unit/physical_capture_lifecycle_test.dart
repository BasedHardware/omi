import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../integration_test/support/physical_capture_lifecycle.dart';

void main() {
  test('successful reporting keeps capture until the deadline and stops exactly once', () {
    fakeAsync((clock) {
      final reporting = Completer<void>();
      var stops = 0;
      var completed = false;
      runBoundedPhysicalCapture(
        duration: const Duration(seconds: 20),
        start: () async {},
        reportStarted: () => reporting.future,
        stop: () async => stops++,
      ).then((_) => completed = true);
      clock.flushMicrotasks();
      clock.elapse(const Duration(seconds: 19));
      expect(stops, 0);
      reporting.complete();
      clock.flushMicrotasks();
      clock.elapse(const Duration(seconds: 1));
      expect(stops, 1);
      expect(completed, isTrue);
      clock.elapse(const Duration(minutes: 1));
      expect(stops, 1);
    });
  });

  test('collector failure stops capture immediately and preserves the failure', () {
    fakeAsync((clock) {
      final reporting = Completer<void>();
      final failure = StateError('collector refused');
      Object? observed;
      var stops = 0;
      runBoundedPhysicalCapture(
        duration: const Duration(seconds: 20),
        start: () async {},
        reportStarted: () => reporting.future,
        stop: () async => stops++,
      ).then<void>((_) {}, onError: (Object error) {
        observed = error;
      });
      clock.flushMicrotasks();
      reporting.completeError(failure);
      clock.flushMicrotasks();
      expect(observed, same(failure));
      expect(stops, 1);
      clock.elapse(const Duration(minutes: 1));
      expect(stops, 1);
    });
  });

  test('stalled reporting cannot extend capture and a late error is consumed', () {
    fakeAsync((clock) {
      final reporting = Completer<void>();
      Object? observed;
      var stops = 0;
      runBoundedPhysicalCapture(
        duration: const Duration(seconds: 20),
        start: () async {},
        reportStarted: () => reporting.future,
        stop: () async => stops++,
      ).then<void>((_) {}, onError: (Object error) {
        observed = error;
      });
      clock.flushMicrotasks();
      clock.elapse(const Duration(seconds: 20));
      expect(stops, 1);
      expect(observed, isA<TimeoutException>());
      reporting.completeError(StateError('late response'));
      clock.flushMicrotasks();
      expect(stops, 1);
    });
  });

  test('mode rejection or partial start failure still stops capture', () async {
    final failure = StateError('unexpected batch mode');
    var stops = 0;
    var reports = 0;
    await expectLater(
      runBoundedPhysicalCapture(
        duration: const Duration(seconds: 20),
        start: () async => throw failure,
        reportStarted: () async => reports++,
        stop: () async => stops++,
      ),
      throwsA(same(failure)),
    );
    expect(stops, 1);
    expect(reports, 0);
  });

  test('cleanup failure preserves both the capture error and cleanup error', () async {
    final captureError = StateError('capture failed');
    final cleanupError = ArgumentError('stop failed');
    await expectLater(
      runBoundedPhysicalCapture(
        duration: const Duration(seconds: 20),
        start: () async => throw captureError,
        reportStarted: () async {},
        stop: () async => throw cleanupError,
      ),
      throwsA(isA<PhysicalCaptureCleanupFailure>()
          .having((failure) => failure.captureError, 'capture error', same(captureError))
          .having((failure) => failure.cleanupError, 'cleanup error', same(cleanupError))),
    );
  });

  test('cleanup failure on a successful capture remains a failed run', () {
    fakeAsync((clock) {
      final cleanupError = StateError('stop failed');
      Object? observed;
      runBoundedPhysicalCapture(
        duration: const Duration(seconds: 20),
        start: () async {},
        reportStarted: () async {},
        stop: () async => throw cleanupError,
      ).then<void>((_) {}, onError: (Object error) {
        observed = error;
      });
      clock.flushMicrotasks();
      clock.elapse(const Duration(seconds: 20));
      expect(observed, isA<PhysicalCaptureCleanupFailure>());
      final failure = observed as PhysicalCaptureCleanupFailure;
      expect(failure.captureError, isNull);
      expect(failure.cleanupError, same(cleanupError));
    });
  });
}
