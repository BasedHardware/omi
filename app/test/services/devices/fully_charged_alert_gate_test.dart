import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/devices/fully_charged_alert_gate.dart';

void main() {
  test('fully-charged dwell is one minute', () {
    expect(FullyChargedAlertGate.minimumOnChargerDwell, const Duration(seconds: 60));
  });

  test('stale cached 100 does not notify before dwell; one fresh 100 after dwell notifies once', () {
    fakeAsync((async) {
      final harness = _Harness(async);
      try {
        harness.sample(100);
        harness.start();
        harness.elapse(const Duration(seconds: 59));
        expect(harness.notifications, isEmpty);
        harness.elapse(const Duration(seconds: 1));
        expect(harness.notifications, isEmpty, reason: 'dwell alone cannot promote a pre-plug sample');

        harness.elapse(const Duration(milliseconds: 1));
        harness.sample(100);
        expect(harness.notifications, [100]);
        harness.elapse(const Duration(minutes: 5));
        harness.sample(100);
        expect(harness.notifications, [100]);
        expect(harness.gate.hasAlerted, isTrue);
      } finally {
        harness.gate.dispose();
      }
    });
  });

  test('fresh 100 during dwell notifies once when the dwell elapses', () {
    fakeAsync((async) {
      final harness = _Harness(async);
      try {
        harness.start();
        harness.elapse(const Duration(seconds: 10));
        harness.sample(100);
        expect(harness.notifications, isEmpty);
        harness.elapse(const Duration(seconds: 49));
        expect(harness.notifications, isEmpty);
        harness.elapse(const Duration(seconds: 1));
        expect(harness.notifications, [100]);
        harness.elapse(const Duration(minutes: 10));
        expect(harness.notifications, [100]);
      } finally {
        harness.gate.dispose();
      }
    });
  });

  test('fresh 66 after dwell does not notify; a later fresh 100 does', () {
    fakeAsync((async) {
      final harness = _Harness(async);
      try {
        harness.start();
        harness.elapse(harness.dwell + const Duration(milliseconds: 1));
        harness.sample(66);
        expect(harness.notifications, isEmpty);
        harness.elapse(const Duration(minutes: 20));
        harness.sample(100);
        expect(harness.notifications, [100]);
      } finally {
        harness.gate.dispose();
      }
    });
  });

  test('a correction below 100 during dwell cancels a pending full reading', () {
    fakeAsync((async) {
      final harness = _Harness(async);
      try {
        harness.start();
        harness.elapse(const Duration(seconds: 5));
        harness.sample(100);
        harness.elapse(const Duration(seconds: 5));
        harness.sample(66);
        harness.elapse(const Duration(minutes: 5));
        expect(harness.notifications, isEmpty);
        expect(harness.mismatches, isEmpty);
      } finally {
        harness.gate.dispose();
      }
    });
  });

  test('unplug during dwell suppresses a later 100 even after the old dwell would have elapsed', () {
    fakeAsync((async) {
      final harness = _Harness(async);
      try {
        harness.start();
        harness.elapse(const Duration(seconds: 15));
        harness.sample(100);
        expect(harness.notifications, isEmpty);
        harness.unplug();
        expect(harness.gate.chargeStartedAt, isNull);
        harness.elapse(const Duration(minutes: 5));
        harness.sample(100);
        expect(harness.notifications, isEmpty);
        expect(harness.gate.hasAlerted, isFalse);
      } finally {
        harness.gate.dispose();
      }
    });
  });

  test('reconnect on charger restarts dwell and ignores samples from the previous edge', () {
    fakeAsync((async) {
      final harness = _Harness(async);
      try {
        harness.start();
        final firstEdge = harness.gate.chargeStartedAt;
        harness.elapse(const Duration(seconds: 50));
        harness.sample(100);
        expect(harness.notifications, isEmpty);

        harness.linkLost();
        harness.elapse(const Duration(seconds: 20));
        harness.start();
        expect(harness.gate.chargeStartedAt!.isAfter(firstEdge!), isTrue);
        // Time left on the old window must not finish the new one, and the
        // pre-reconnect sample is not after the new edge.
        harness.elapse(const Duration(seconds: 10));
        expect(harness.notifications, isEmpty);

        harness.elapse(const Duration(milliseconds: 1));
        harness.sample(100);
        expect(harness.notifications, isEmpty);
        harness.elapse(harness.dwell - const Duration(seconds: 10) - const Duration(milliseconds: 1));
        expect(harness.notifications, [100]);
      } finally {
        harness.gate.dispose();
      }
    });
  });

  test('a lower reading after notify is logged once and does not retract or re-notify', () {
    fakeAsync((async) {
      final harness = _Harness(async);
      try {
        harness.start();
        harness.elapse(harness.dwell + const Duration(milliseconds: 1));
        harness.sample(100);
        expect(harness.notifications, [100]);

        harness.elapse(const Duration(seconds: 1));
        harness.sample(66);
        harness.sample(64);
        expect(harness.notifications, [100]);
        expect(harness.mismatches, [(notifiedAtLevel: 100, correctedLevel: 66)]);
        expect(harness.gate.hasAlerted, isTrue);

        harness.elapse(const Duration(seconds: 1));
        harness.sample(100);
        expect(harness.notifications, [100]);
      } finally {
        harness.gate.dispose();
      }
    });
  });

  test('device B notifies after device A already alerted when B charges from 66 to 100', () {
    fakeAsync((async) {
      final harness = _Harness(async);
      try {
        harness.start('A');
        harness.elapse(harness.dwell + const Duration(milliseconds: 1));
        harness.sample(100, id: 'A');
        expect(harness.notifications, [100]);

        harness.linkLost('A');
        harness.start('B');
        harness.elapse(const Duration(milliseconds: 1));
        harness.sample(66, id: 'B');
        expect(harness.notifications, [100]);

        harness.elapse(const Duration(minutes: 30));
        harness.sample(100, id: 'B');
        expect(harness.notifications, [100, 100]);
        expect(harness.gate.hasAlertedFor('A'), isTrue);
        expect(harness.gate.hasAlertedFor('B'), isTrue);
      } finally {
        harness.gate.dispose();
      }
    });
  });

  test('device A notifies again after an unobserved unplug while disconnected and a reconnect below 100', () {
    fakeAsync((async) {
      final harness = _Harness(async);
      try {
        harness.start('A');
        harness.elapse(harness.dwell + const Duration(milliseconds: 1));
        harness.sample(100, id: 'A');
        expect(harness.notifications, [100]);

        // Link drops. The unplug and replug happen while disconnected, so
        // onUnplugged is never observed.
        harness.linkLost('A');
        harness.elapse(const Duration(minutes: 20));
        harness.start('A');
        harness.elapse(const Duration(milliseconds: 1));
        harness.sample(66, id: 'A');
        expect(harness.notifications, [100]);
        expect(harness.gate.hasAlertedFor('A'), isFalse);

        harness.elapse(harness.dwell);
        harness.sample(100, id: 'A');
        expect(harness.notifications, [100, 100]);
      } finally {
        harness.gate.dispose();
      }
    });
  });

  test('reconnect while still reporting 100 does not notify again', () {
    fakeAsync((async) {
      final harness = _Harness(async);
      try {
        harness.start('A');
        harness.elapse(harness.dwell + const Duration(milliseconds: 1));
        harness.sample(100, id: 'A');
        harness.linkLost('A');
        harness.start('A');
        harness.elapse(harness.dwell + const Duration(milliseconds: 1));
        harness.sample(100, id: 'A');
        expect(harness.notifications, [100]);
      } finally {
        harness.gate.dispose();
      }
    });
  });

  test('a fifth device still notifies and the oldest disconnected cycle is dropped', () {
    fakeAsync((async) {
      final harness = _Harness(async);
      try {
        for (final id in ['a', 'b', 'c', 'd']) {
          harness.start(id);
          harness.elapse(harness.dwell + const Duration(milliseconds: 1));
          harness.sample(100, id: id);
          harness.linkLost(id);
          harness.elapse(const Duration(milliseconds: 1));
        }
        expect(harness.notifications, [100, 100, 100, 100]);

        harness.start('e');
        harness.elapse(const Duration(milliseconds: 1));
        harness.sample(66, id: 'e');
        harness.elapse(harness.dwell);
        harness.sample(100, id: 'e');
        expect(harness.notifications, [100, 100, 100, 100, 100]);

        // 'a' was the oldest disconnected identity and was evicted, so a new
        // charge cycle on it can notify. A retained alert would suppress this.
        harness.start('a');
        harness.elapse(harness.dwell + const Duration(milliseconds: 1));
        harness.sample(100, id: 'a');
        expect(harness.notifications, [100, 100, 100, 100, 100, 100]);
      } finally {
        harness.gate.dispose();
      }
    });
  });

  test('wall-clock advance of two minutes after one real second does not notify until monotonic dwell elapses', () {
    fakeAsync((async) {
      final harness = _Harness(async);
      try {
        harness.start();
        harness.elapse(const Duration(seconds: 1));
        harness.advanceWall(const Duration(minutes: 2));
        harness.sample(100);
        expect(harness.notifications, isEmpty, reason: 'wall time is past the dwell; monotonic time is not');

        harness.elapse(const Duration(seconds: 58));
        expect(harness.notifications, isEmpty);
        harness.elapse(const Duration(seconds: 1));
        expect(harness.notifications, [100]);
      } finally {
        harness.gate.dispose();
      }
    });
  });

  test('sample timestamped before the charge edge stays excluded', () {
    fakeAsync((async) {
      final harness = _Harness(async);
      try {
        harness.start();
        final edge = harness.gate.chargeStartedAt!;
        harness.elapse(harness.dwell + const Duration(milliseconds: 1));

        harness.sample(100,
            at: edge.subtract(FullyChargedAlertGate.preEdgeStaleTolerance + const Duration(milliseconds: 1)));
        expect(harness.notifications, isEmpty, reason: 'earlier than the edge by more than the tolerance is pre-edge');

        harness.sample(100, at: edge.subtract(const Duration(milliseconds: 1)));
        expect(harness.notifications, isEmpty, reason: 'inside the tolerance but not after the edge is still stale');

        harness.sample(100, at: edge);
        expect(harness.notifications, isEmpty, reason: 'a sample stamped at the edge is the cached reading');

        harness.sample(100);
        expect(harness.notifications, [100]);
      } finally {
        harness.gate.dispose();
      }
    });
  });

  test('a lower reading is not a mismatch attempt until presentation is confirmed', () {
    fakeAsync((async) {
      final harness = _Harness(async, confirmPresentation: false);
      try {
        harness.start();
        harness.elapse(harness.dwell + const Duration(milliseconds: 1));
        harness.sample(100);
        expect(harness.notifications, [100]);

        harness.elapse(const Duration(seconds: 1));
        harness.sample(66);
        expect(harness.mismatches, isEmpty);

        harness.gate.markPresented(_Harness.device);
        expect(harness.mismatches, [(notifiedAtLevel: 100, correctedLevel: 66)]);
      } finally {
        harness.gate.dispose();
      }
    });
  });
}

typedef _Mismatch = ({int notifiedAtLevel, int correctedLevel});

class _Harness {
  _Harness(this.async, {this.confirmPresentation = true}) {
    gate = FullyChargedAlertGate(
      now: () => wall,
      monotonicNow: () => async.elapsed,
      onFullyCharged: (level) {
        notifications.add(level);
        if (!confirmPresentation) return;
        final id = gate.lastFiredDeviceId;
        if (id != null) gate.markPresented(id);
      },
      onLevelMismatch: ({required int notifiedAtLevel, required int correctedLevel}) {
        mismatches.add((notifiedAtLevel: notifiedAtLevel, correctedLevel: correctedLevel));
      },
    );
  }

  static const device = 'pendant';

  final FakeAsync async;
  final bool confirmPresentation;
  late final FullyChargedAlertGate gate;
  final notifications = <int>[];
  final mismatches = <_Mismatch>[];
  var wall = DateTime.utc(2026, 10, 11, 8);

  Duration get dwell => gate.minimumDwell;

  void start([String id = device]) => gate.onChargeStarted(id);

  void unplug([String id = device]) => gate.onUnplugged(id);

  void linkLost([String id = device]) => gate.onLinkLost(id);

  void sample(int level, {String id = device, DateTime? at}) => gate.onBatterySample(id, level, at: at);

  void elapse(Duration duration) {
    wall = wall.add(duration);
    async.elapse(duration);
  }

  void advanceWall(Duration duration) {
    wall = wall.add(duration);
  }
}
