import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import '../support/capture/virtual_capture_time.dart';
import '../support/spine/contract.dart';
import 'package:omi/services/capture/capture_lifetime.dart';

CaptureLifetime lifetime() => CaptureLifetime(ManualScheduler(clock: VirtualClock(DateTime.utc(2026))));

void main() {
  contractTest('concurrent close joins outstanding cancellation', () async {
    final bag = lifetime();
    final gate = Completer<void>();
    bag.own(() => gate.future);
    final first = bag.close();
    var secondFinished = false;
    final second = bag.close().then((_) => secondFinished = true);
    await pumpEventQueue();
    final finishedBeforeRelease = secondFinished;
    gate.complete();
    await Future.wait([first, second]);
    expect(finishedBeforeRelease, isFalse);
  });
  contractTest('asFuture preserves completion untracking', () async {
    final bag = lifetime();
    final controller = StreamController<int>();
    final sub = bag.listen(controller.stream, (_) {});
    expect(bag.debugTrackedCount, 1);
    final done = sub.asFuture<void>();
    await controller.close();
    await done;
    final retained = bag.debugTrackedCount;
    await bag.close();
    expect(retained, 0);
  });
  contractTest('replaced callbacks and errors stay closed while cancellation drains', () async {
    final bag = lifetime();
    final gate = Completer<void>();
    bag.own(() => gate.future);
    final controller = StreamController<int>.broadcast(sync: true);
    final events = <String>[];
    final sub =
        bag.listen(controller.stream, (_) => events.add('original'), onError: (Object _) => events.add('error'));
    sub.onData((_) => events.add('replacement'));
    controller.add(0);
    controller.addError(StateError('before-close'));
    expect(events, ['replacement', 'error']);
    events.clear();
    final closing = bag.close();
    controller.add(1);
    controller.addError(StateError('late'));
    final leaked = List.of(events);
    gate.complete();
    await closing;
    await controller.close();
    expect(leaked, isEmpty);
  });
}
