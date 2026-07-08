import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/capture_metrics_tracker.dart';

void main() {
  test('notifies when first metrics listener is added', () {
    var notifyCount = 0;
    final tracker = CaptureMetricsTracker(onNotify: () => notifyCount++);

    tracker.addMetricsListener();
    tracker.addMetricsListener();

    expect(notifyCount, 1);
  });

  test('calculate only notifies while metrics listeners are registered', () {
    var notifyCount = 0;
    final tracker = CaptureMetricsTracker(onNotify: () => notifyCount++);

    tracker.addBleBytes(1000);
    tracker.addSocketBytes(500);
    tracker.calculateForTesting();
    expect(notifyCount, 0);

    var listenedNotifyCount = 0;
    final listenedTracker = CaptureMetricsTracker(onNotify: () => listenedNotifyCount++);
    listenedTracker.addMetricsListener();
    final countAfterAdd = listenedNotifyCount;
    listenedTracker.addBleBytes(1000);
    listenedTracker.addSocketBytes(500);
    listenedTracker.calculateForTesting();

    expect(listenedNotifyCount, greaterThan(countAfterAdd));
    expect(listenedTracker.bleReceiveRateKbps, greaterThan(0));
    expect(listenedTracker.wsSendRateKbps, greaterThan(0));
  });
}
