import 'package:fake_async/fake_async.dart';
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

  test('pauses the UI sampler in background while lifetime byte counters continue', () {
    fakeAsync((async) {
      var notifyCount = 0;
      final tracker = CaptureMetricsTracker(onNotify: () => notifyCount++);
      tracker.addMetricsListener();
      tracker.start();

      expect(tracker.isSampling, isTrue);
      tracker.addBleBytes(100);
      tracker.addSocketBytes(50);

      tracker.setAppActive(false);
      final notificationsAtPause = notifyCount;
      tracker.addBleBytes(200);
      tracker.addSocketBytes(75);
      async.elapse(const Duration(seconds: 20));

      expect(tracker.isSampling, isFalse);
      expect(notifyCount, notificationsAtPause);
      expect(tracker.lifetimeBleBytesReceived, 300);
      expect(tracker.lifetimeWsSocketBytesSent, 125);

      tracker.setAppActive(true);
      expect(tracker.isSampling, isTrue);
      tracker.dispose();
    });
  });
}
