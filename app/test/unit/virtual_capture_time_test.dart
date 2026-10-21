import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import '../support/capture/virtual_capture_time.dart';

void main() {
  test('elapse keeps an async periodic callback in-flight until waitForCallbackIo', () async {
    final clock = VirtualClock(DateTime.utc(2026, 1, 1));
    final scheduler = ManualScheduler(clock: clock);
    final started = Completer<void>();
    final finish = Completer<void>();

    scheduler.periodic(const Duration(seconds: 1), (timer) async {
      started.complete();
      await finish.future;
    });

    scheduler.elapse(const Duration(seconds: 1));
    expect(started.isCompleted, isTrue, reason: 'the due callback must have been invoked');
    expect(scheduler.hasInFlightIo, isTrue, reason: 'virtual-time idle is not durable I/O');

    var ioDone = false;
    final waiting = scheduler.waitForCallbackIo().then((_) {
      ioDone = true;
    });
    await pumpEventQueue();
    expect(ioDone, isFalse, reason: 'waitForCallbackIo must not complete while the callback Future is parked');

    finish.complete();
    await waiting;
    expect(scheduler.hasInFlightIo, isFalse);
  });

  test('waitForCallbackIo is a no-op when every fired callback was synchronous', () async {
    final clock = VirtualClock(DateTime.utc(2026, 1, 1));
    final scheduler = ManualScheduler(clock: clock);
    var fires = 0;
    scheduler.periodic(const Duration(seconds: 1), (timer) {
      fires++;
    });
    scheduler.elapse(const Duration(seconds: 1));
    expect(fires, 1);
    expect(scheduler.hasInFlightIo, isFalse);
    await scheduler.waitForCallbackIo();
    expect(fires, 1);
  });
}
