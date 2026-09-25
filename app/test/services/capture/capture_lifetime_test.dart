import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/capture_lifetime.dart';

import '../../support/capture/virtual_capture_time.dart';

void main() {
  test('close does not cancel timers the bag did not register', () async {
    final scheduler = ManualScheduler(clock: VirtualClock(DateTime.utc(2026)));
    final events = <String>[];
    scheduler.once(const Duration(seconds: 1), () => events.add('foreign'));
    final bag = CaptureLifetime(scheduler);
    bag.once(const Duration(seconds: 1), () => events.add('owned'));
    await bag.close();
    scheduler.elapse(const Duration(seconds: 1));
    expect(events, ['foreign']);
    expect(scheduler.pendingTimers, isEmpty);
  });

  test('once after close never fires', () async {
    final scheduler = ManualScheduler(clock: VirtualClock(DateTime.utc(2026)));
    final bag = CaptureLifetime(scheduler);
    await bag.close();
    final events = <String>[];
    bag.once(const Duration(seconds: 1), () => events.add('late-once'));
    scheduler.elapse(const Duration(minutes: 1));
    expect(events, isEmpty);
    expect(scheduler.pendingTimers, isEmpty);
    expect(bag.debugTrackedCount, 0);
  });

  test('close invalidates before awaiting a slow cancel so a mid-close once dies', () async {
    final scheduler = ManualScheduler(clock: VirtualClock(DateTime.utc(2026)));
    final bag = CaptureLifetime(scheduler);
    final gate = Completer<void>();
    bag.own(() => gate.future);
    final closing = bag.close();
    await pumpEventQueue();
    final events = <String>[];
    bag.once(const Duration(seconds: 1), () => events.add('during-close'));
    gate.complete();
    await closing;
    scheduler.elapse(const Duration(seconds: 1));
    expect(events, isEmpty);
    expect(scheduler.pendingTimers, isEmpty);
  });

  test('every cancel runs when two releases fail; the first error is rethrown', () async {
    final bag = CaptureLifetime(ManualScheduler(clock: VirtualClock(DateTime.utc(2026))));
    final ran = <int>[];
    bag.own(() {
      ran.add(1);
      throw StateError('first');
    });
    bag.own(() {
      ran.add(2);
      throw StateError('second');
    });
    await expectLater(bag.close(), throwsA(isA<StateError>().having((e) => e.message, 'message', 'first')));
    expect(ran, [1, 2]);
    await bag.close();
  });

  test('fired once timers leave the bag', () async {
    final scheduler = ManualScheduler(clock: VirtualClock(DateTime.utc(2026)));
    final bag = CaptureLifetime(scheduler);
    var fired = 0;
    for (var i = 0; i < 8; i++) {
      bag.once(const Duration(seconds: 1), () => fired++);
    }
    expect(bag.debugTrackedCount, 8);
    scheduler.elapse(const Duration(seconds: 1));
    expect(fired, 8);
    expect(bag.debugTrackedCount, 0);
    await bag.close();
    expect(bag.debugTrackedCount, 0);
  });

  test('once untracks before invoking a throwing callback', () {
    final scheduler = ManualScheduler(clock: VirtualClock(DateTime.utc(2026)));
    final bag = CaptureLifetime(scheduler);
    bag.once(const Duration(seconds: 1), () => throw StateError('callback'));
    expect(bag.debugTrackedCount, 1);
    expect(() => scheduler.elapse(const Duration(seconds: 1)), throwsA(isA<StateError>()));
    expect(bag.debugTrackedCount, 0);
  });

  test('caller-side cancel untracks and close does not run it again', () async {
    final scheduler = ManualScheduler(clock: VirtualClock(DateTime.utc(2026)));
    final bag = CaptureLifetime(scheduler);
    var ownCancels = 0;
    final owned = bag.own(() => ownCancels++);
    final timer = bag.once(const Duration(seconds: 1), () {});
    expect(bag.debugTrackedCount, 2);
    timer.cancel();
    expect(timer.isActive, isFalse);
    await owned.release();
    expect(ownCancels, 1);
    expect(bag.debugTrackedCount, 0);
    await bag.close();
    await bag.close();
    expect(ownCancels, 1);
    expect(bag.debugTrackedCount, 0);
  });

  test('a completed stream is untracked', () async {
    final bag = CaptureLifetime(ManualScheduler(clock: VirtualClock(DateTime.utc(2026))));
    final stream = StreamController<int>.broadcast(sync: true);
    final sub = bag.listen(stream.stream, (_) {});
    expect(bag.debugTrackedCount, 1);
    await stream.close();
    expect(bag.debugTrackedCount, 0);
    await sub.cancel();
    await bag.close();
    expect(bag.debugTrackedCount, 0);
  });

  test('listen forwards onError and cancelOnError untracks', () async {
    final bag = CaptureLifetime(ManualScheduler(clock: VirtualClock(DateTime.utc(2026))));
    final forwarded = StreamController<int>.broadcast(sync: true);
    Object? seen;
    bag.listen(forwarded.stream, (_) {}, onError: (Object e) => seen = e);
    forwarded.addError(StateError('forwarded'));
    expect(seen, isA<StateError>());
    expect(bag.debugTrackedCount, 1);

    final auto = StreamController<int>.broadcast(sync: true);
    bag.listen(auto.stream, (_) {}, onError: (Object _) {}, cancelOnError: true);
    expect(bag.debugTrackedCount, 2);
    auto.addError(StateError('auto'));
    expect(bag.debugTrackedCount, 1);

    await forwarded.close();
    await auto.close();
    await bag.close();
  });

  test('close after completed work still drains survivors when one throws', () async {
    final scheduler = ManualScheduler(clock: VirtualClock(DateTime.utc(2026)));
    final bag = CaptureLifetime(scheduler);
    var fired = 0;
    for (var i = 0; i < 3; i++) {
      bag.once(const Duration(seconds: 1), () => fired++);
    }
    scheduler.elapse(const Duration(seconds: 1));
    expect(fired, 3);
    bag.once(const Duration(seconds: 1), () {}).cancel();
    final stream = StreamController<int>.broadcast(sync: true);
    bag.listen(stream.stream, (_) {});
    await stream.close();
    expect(bag.debugTrackedCount, 0);

    var surviving = 0;
    bag.own(() => throw StateError('cancel failure'));
    bag.own(() => surviving++);
    expect(bag.debugTrackedCount, 2);
    await expectLater(bag.close(), throwsA(isA<StateError>()));
    expect(surviving, 1);
    await bag.close();
    expect(bag.debugTrackedCount, 0);
  });

  test('close cancels every owned timer so nothing fires afterwards', () async {
    final scheduler = ManualScheduler(clock: VirtualClock(DateTime.utc(2026)));
    final bag = CaptureLifetime(scheduler);
    var fired = 0;
    bag.once(const Duration(seconds: 1), () => fired++);
    bag.once(const Duration(seconds: 2), () => fired++);
    bag.periodic(const Duration(seconds: 1), (_) => fired++);
    await bag.close();
    expect(scheduler.pendingTimers, isEmpty);
    scheduler.elapse(const Duration(seconds: 5));
    expect(fired, 0);
  });

  test('concurrent close joins the in-flight drain; a later close is a no-op', () async {
    final bag = CaptureLifetime(ManualScheduler(clock: VirtualClock(DateTime.utc(2026))));
    final gate = Completer<void>();
    bag.own(() => gate.future);
    final first = bag.close();
    var secondFinished = false;
    final second = bag.close().then((_) => secondFinished = true);
    await pumpEventQueue();
    expect(secondFinished, isFalse);
    gate.complete();
    await Future.wait([first, second]);
    expect(secondFinished, isTrue);
    await bag.close();
  });

  test('asFuture untracks on completion and on error', () async {
    final bag = CaptureLifetime(ManualScheduler(clock: VirtualClock(DateTime.utc(2026))));
    final completed = StreamController<int>();
    final completedSub = bag.listen(completed.stream, (_) {});
    expect(bag.debugTrackedCount, 1);
    final done = completedSub.asFuture<void>();
    await completed.close();
    await done;
    expect(bag.debugTrackedCount, 0);
    await bag.close();

    final failing = CaptureLifetime(ManualScheduler(clock: VirtualClock(DateTime.utc(2026))));
    final errors = StreamController<int>();
    final errorSub = failing.listen(errors.stream, (_) {});
    expect(failing.debugTrackedCount, 1);
    final expected = expectLater(errorSub.asFuture<void>(), throwsStateError);
    errors.addError(StateError('synthetic'));
    await expected;
    await errors.close();
    expect(failing.debugTrackedCount, 0);
    await failing.close();
  });

  test('replacement data and error callbacks do not run after close begins', () async {
    final bag = CaptureLifetime(ManualScheduler(clock: VirtualClock(DateTime.utc(2026))));
    final gate = Completer<void>();
    bag.own(() => gate.future);
    final controller = StreamController<int>.broadcast(sync: true);
    final events = <String>[];
    final sub = bag.listen(
      controller.stream,
      (_) => events.add('original'),
      onError: (Object _) => events.add('error'),
    );
    sub.onData((_) => events.add('replacement'));
    controller.add(0);
    controller.addError(StateError('before-close'));
    expect(events, ['replacement', 'error']);
    events.clear();
    final closing = bag.close();
    controller.add(1);
    controller.addError(StateError('late'));
    expect(events, isEmpty);
    gate.complete();
    await closing;
    await controller.close();
  });

  test('original and replacement onDone do not run after close begins', () async {
    for (final replace in [false, true]) {
      final bag = CaptureLifetime(ManualScheduler(clock: VirtualClock(DateTime.utc(2026))));
      final completed = StreamController<int>();
      var delivered = 0;
      bag.listen(completed.stream, (_) {}, onDone: () => delivered++);
      await completed.close();
      expect(delivered, 1);
      expect(bag.debugTrackedCount, 0);
      final gate = Completer<void>();
      bag.own(() => gate.future);
      final stream = StreamController<int>();
      final sub = bag.listen(stream.stream, (_) {}, onDone: () => delivered++);
      if (replace) sub.onDone(() => delivered += 2);
      final closing = bag.close();
      final done = stream.close();
      await pumpEventQueue();
      final leaked = delivered;
      gate.complete();
      await closing;
      await done;
      expect(leaked, 1, reason: 'completion may untrack, but cannot call the closed owner');
    }
  });
}
