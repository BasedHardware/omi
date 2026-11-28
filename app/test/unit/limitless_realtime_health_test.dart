import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/devices/connectors/limitless_realtime_health.dart';

void main() {
  const window = Duration(seconds: 8);
  const cadence = Duration(seconds: 2);

  test('mid-stream stall retries once and sustained decoded audio rearms the budget', () {
    fakeAsync((time) {
      var writes = 0;
      final outcomes = <LimitlessRealtimeHealthOutcome>[];
      final monitor = LimitlessRealtimeHealth(
        window: window,
        elapsed: () => time.elapsed,
        isCurrent: () => true,
        reactivate: () async {
          writes++;
          return true;
        },
        report: outcomes.add,
      );

      for (var i = 0; i < 5; i++) {
        time.elapse(cadence);
        monitor.observeFrame();
      }
      expect(writes, 0);
      time.elapse(window);
      expect(writes, 1);

      for (var i = 0; i < 5; i++) {
        time.elapse(cadence);
        monitor.observeFrame();
      }
      expect(outcomes, [LimitlessRealtimeHealthOutcome.restored]);
      time.elapse(window);
      expect(writes, 2);
      monitor.close();
      expect(outcomes.last, LimitlessRealtimeHealthOutcome.censored);
    });
  });

  test('a successful enable without decoded audio gets one bounded retry', () {
    fakeAsync((time) {
      var attempts = 0;
      final outcomes = <LimitlessRealtimeHealthOutcome>[];
      final monitor = LimitlessRealtimeHealth(
        window: window,
        elapsed: () => time.elapsed,
        isCurrent: () => true,
        reactivate: () async {
          attempts++;
          return true;
        },
        report: outcomes.add,
      );

      time.elapse(window);
      time.flushMicrotasks();
      expect(attempts, 1);
      time.elapse(window);
      time.flushMicrotasks();
      expect(attempts, 2);
      time.elapse(window);
      expect(outcomes, [LimitlessRealtimeHealthOutcome.exhausted]);
      monitor.close();
    });
  });

  test('isolated frames and a hanging write cannot reset the recovery budget', () {
    fakeAsync((time) {
      var writes = 0;
      final pendingWrite = Completer<bool>();
      final outcomes = <LimitlessRealtimeHealthOutcome>[];
      final monitor = LimitlessRealtimeHealth(
        window: window,
        elapsed: () => time.elapsed,
        isCurrent: () => true,
        reactivate: () {
          writes++;
          return pendingWrite.future;
        },
        report: outcomes.add,
        reactivationTimeout: window * 3,
      );

      time.elapse(window);
      monitor.observeFrame();
      time.elapse(const Duration(seconds: 9));
      monitor.observeFrame();
      time.elapse(window * 3);
      expect(writes, 1);
      expect(outcomes, [LimitlessRealtimeHealthOutcome.exhausted]);
      pendingWrite.complete(true);
      time.flushMicrotasks();
      monitor.close();
      expect(outcomes, hasLength(1));
    });
  });

  test('a skipped enable gets one bounded retry before the episode expires', () {
    fakeAsync((time) {
      var current = true;
      var attempts = 0;
      final outcomes = <LimitlessRealtimeHealthOutcome>[];
      final monitor = LimitlessRealtimeHealth(
        window: window,
        elapsed: () => time.elapsed,
        isCurrent: () => current,
        reactivate: () async {
          attempts++;
          return attempts > 1;
        },
        report: outcomes.add,
      );

      time.elapse(window);
      time.flushMicrotasks();
      expect(attempts, 1);
      expect(outcomes, isEmpty);

      time.elapse(window);
      time.flushMicrotasks();
      expect(attempts, 2);
      time.elapse(window * 2);
      expect(outcomes, [LimitlessRealtimeHealthOutcome.exhausted]);
      current = false;
      monitor.close();
    });
  });

  test('throwing enable writes retry once and finish with an exhausted outcome', () {
    fakeAsync((time) {
      var attempts = 0;
      final outcomes = <LimitlessRealtimeHealthOutcome>[];
      final monitor = LimitlessRealtimeHealth(
        window: window,
        elapsed: () => time.elapsed,
        isCurrent: () => true,
        reactivate: () async {
          attempts++;
          throw StateError('BLE write failed');
        },
        report: outcomes.add,
      );

      time.elapse(window);
      time.flushMicrotasks();
      expect(attempts, 1);
      time.elapse(window);
      time.flushMicrotasks();
      expect(attempts, 2);
      time.elapse(window);
      expect(outcomes, [LimitlessRealtimeHealthOutcome.exhausted]);
      time.elapse(window * 5);
      expect(attempts, 2, reason: 'a failed episode is bounded instead of retrying forever');
      monitor.close();
    });
  });

  test('a timed out reactivation releases the in-flight guard for its bounded retry', () {
    fakeAsync((time) {
      var attempts = 0;
      final outcomes = <LimitlessRealtimeHealthOutcome>[];
      final neverCompletes = Completer<bool>();
      final monitor = LimitlessRealtimeHealth(
        window: window,
        elapsed: () => time.elapsed,
        isCurrent: () => true,
        reactivate: () {
          attempts++;
          return neverCompletes.future;
        },
        report: outcomes.add,
        reactivationTimeout: const Duration(seconds: 2),
      );

      time.elapse(window);
      time.flushMicrotasks();
      expect(attempts, 1);
      time.elapse(window + const Duration(seconds: 2));
      time.flushMicrotasks();
      expect(attempts, 2, reason: 'a never completing call cannot hold the retry guard forever');
      time.elapse(window * 2);
      expect(outcomes, [LimitlessRealtimeHealthOutcome.exhausted]);
      monitor.close();
    });
  });

  test('ownership loss before or during recovery fences the write and censors an in-flight stall', () {
    fakeAsync((time) {
      var current = true;
      var writes = 0;
      final pendingWrite = Completer<bool>();
      final outcomes = <LimitlessRealtimeHealthOutcome>[];
      LimitlessRealtimeHealth start() => LimitlessRealtimeHealth(
            window: window,
            elapsed: () => time.elapsed,
            isCurrent: () => current,
            reactivate: () {
              writes++;
              return pendingWrite.future;
            },
            report: outcomes.add,
          );

      start();
      current = false;
      time.elapse(window);
      expect(writes, 0);
      expect(outcomes, isEmpty);

      current = true;
      start();
      time.elapse(window);
      expect(writes, 1);
      current = false;
      pendingWrite.complete(true);
      time.flushMicrotasks();
      time.elapse(window * 3);
      expect(writes, 1);
      expect(outcomes, [LimitlessRealtimeHealthOutcome.censored]);
    });
  });
}
