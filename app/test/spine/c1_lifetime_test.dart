import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/capture_lifetime.dart';
import '../support/capture/virtual_capture_time.dart';
import '../support/spine/contract.dart';

void main() {
  contractTest('C1 lifetime cancels every timer, stream, and listener including late acquisition', () async {
    final scheduler = ManualScheduler(clock: VirtualClock(DateTime.utc(2026)));
    final bag = CaptureLifetime(scheduler);
    final stream = StreamController<int>.broadcast(sync: true);
    final events = <String>[];
    var removals = 0;
    bag.once(const Duration(seconds: 1), () => events.add('once'));
    bag.periodic(const Duration(seconds: 1), (_) => events.add('periodic'));
    bag.listen(stream.stream, (v) => events.add('$v'));
    bag.own(() {
      removals++;
    });
    stream.add(1);
    scheduler.elapse(const Duration(seconds: 1));
    expect(events, ['1', 'once', 'periodic']);
    await bag.close();
    await bag.close();
    expect(removals, 1);
    expect(stream.hasListener, isFalse);
    expect(scheduler.pendingTimers, isEmpty);
    // Registration after disposal immediately cancels; it never resurrects work.
    bag.own(() {
      removals++;
    });
    bag.periodic(const Duration(seconds: 1), (_) => events.add('late'));
    bag.listen(stream.stream, (v) => events.add('late-stream'));
    await pumpEventQueue();
    stream.add(2);
    scheduler.elapse(const Duration(minutes: 1));
    expect(events, ['1', 'once', 'periodic']);
    expect(removals, 2);
    expect(scheduler.pendingTimers, isEmpty);
    expect(stream.hasListener, isFalse);
    await stream.close();
  });

  contractTest('C1 one failed cancellation cannot strand other resources', () async {
    final bag = CaptureLifetime(ManualScheduler(clock: VirtualClock(DateTime.utc(2026))));
    var cancelled = false;
    bag.own(() => throw StateError('cancel failure'));
    bag.own(() {
      cancelled = true;
    });
    await expectLater(bag.close(), throwsStateError);
    expect(cancelled, isTrue);
    await bag.close();
  });
}
