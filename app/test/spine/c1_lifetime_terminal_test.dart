import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/capture_lifetime.dart';
import '../support/capture/virtual_capture_time.dart';
import '../support/spine/contract.dart';

CaptureLifetime lifetime() => CaptureLifetime(ManualScheduler(clock: VirtualClock(DateTime.utc(2026))));

void main() {
  contractTest('C1 asFuture error completion releases its registration', () async {
    final bag = lifetime();
    final stream = StreamController<int>();
    final sub = bag.listen(stream.stream, (_) {});
    expect(bag.debugTrackedCount, 1);
    final expected = expectLater(sub.asFuture<void>(), throwsStateError);
    stream.addError(StateError('synthetic'));
    await expected;
    await stream.close();
    final retained = bag.debugTrackedCount;
    await bag.close();
    expect(retained, 0);
  });
  contractTest('C1 original and replacement done callbacks respect closing', () async {
    for (final replace in [false, true]) {
      final bag = lifetime();
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
