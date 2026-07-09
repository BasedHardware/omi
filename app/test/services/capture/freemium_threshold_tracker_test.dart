import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/services/capture/freemium_threshold_tracker.dart';

void main() {
  test('handles first threshold event and ignores duplicates', () {
    final tracker = FreemiumThresholdTracker();

    final firstHandled = tracker.handle(
      FreemiumThresholdReachedEvent(remainingSeconds: 180, action: FreemiumAction.setupOnDeviceStt),
    );
    final secondHandled = tracker.handle(
      FreemiumThresholdReachedEvent(remainingSeconds: 30, action: FreemiumAction.none),
    );

    expect(firstHandled, isTrue);
    expect(secondHandled, isFalse);
    expect(tracker.reached, isTrue);
    expect(tracker.remainingSeconds, 180);
    expect(tracker.requiresUserAction, isTrue);
  });

  test('reset clears threshold state', () {
    final tracker = FreemiumThresholdTracker();
    tracker.handle(FreemiumThresholdReachedEvent(remainingSeconds: 180, action: FreemiumAction.setupOnDeviceStt));

    tracker.reset();

    expect(tracker.reached, isFalse);
    expect(tracker.remainingSeconds, 0);
    expect(tracker.requiresUserAction, isFalse);
  });
}
