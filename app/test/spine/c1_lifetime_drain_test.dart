import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import '../support/capture/virtual_capture_time.dart';
import '../support/spine/contract.dart';
import 'package:omi/services/capture/capture_lifetime.dart';

CaptureLifetime lifetime() => CaptureLifetime(ManualScheduler(clock: VirtualClock(DateTime.utc(2026))));
void main() {
  contractTest('close joins a release already in flight', () async {
    final bag = lifetime();
    final gate = Completer<void>();
    var cancellations = 0;
    final owned = bag.own(() {
      cancellations++;
      return gate.future;
    });
    final release = owned.release();
    var finished = false;
    final closing = bag.close().then((_) => finished = true);
    await pumpEventQueue();
    final premature = finished;
    gate.complete();
    await Future.wait([release, closing]);
    expect(cancellations, 1);
    expect(premature, isFalse);
  });
  contractTest('close joins explicit subscription cancellation already in flight', () async {
    final gate = Completer<void>();
    final stream = StreamController<int>(onCancel: () => gate.future);
    final bag = lifetime();
    final sub = bag.listen(stream.stream, (_) {});
    final cancellation = sub.cancel();
    var finished = false;
    final closing = bag.close().then((_) => finished = true);
    await pumpEventQueue();
    final premature = finished;
    gate.complete();
    await Future.wait([cancellation, closing]);
    await stream.close();
    expect(premature, isFalse);
  });
}
