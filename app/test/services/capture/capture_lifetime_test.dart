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
}
