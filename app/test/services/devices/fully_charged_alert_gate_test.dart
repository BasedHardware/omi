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
        harness.gate.onBatterySample(100);
        harness.gate.onChargeStarted();
        harness.elapse(const Duration(seconds: 59));
        expect(harness.notifications, isEmpty);
        harness.elapse(const Duration(seconds: 1));
        expect(harness.notifications, isEmpty, reason: 'dwell alone cannot promote a pre-plug sample');

        harness.elapse(const Duration(milliseconds: 1));
        harness.gate.onBatterySample(100);
        expect(harness.notifications, [100]);
        harness.elapse(const Duration(minutes: 5));
        harness.gate.onBatterySample(100);
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
        harness.gate.onChargeStarted();
        harness.elapse(const Duration(seconds: 10));
        harness.gate.onBatterySample(100);
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
        harness.gate.onChargeStarted();
        harness.elapse(harness.dwell + const Duration(milliseconds: 1));
        harness.gate.onBatterySample(66);
        expect(harness.notifications, isEmpty);
        harness.elapse(const Duration(minutes: 20));
        harness.gate.onBatterySample(100);
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
        harness.gate.onChargeStarted();
        harness.elapse(const Duration(seconds: 5));
        harness.gate.onBatterySample(100);
        harness.elapse(const Duration(seconds: 5));
        harness.gate.onBatterySample(66);
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
        harness.gate.onChargeStarted();
        harness.elapse(const Duration(seconds: 15));
        harness.gate.onBatterySample(100);
        expect(harness.notifications, isEmpty);
        harness.gate.onUnplugged();
        expect(harness.gate.chargeStartedAt, isNull);
        harness.elapse(const Duration(minutes: 5));
        harness.gate.onBatterySample(100);
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
        harness.gate.onChargeStarted();
        final firstEdge = harness.gate.chargeStartedAt;
        harness.elapse(const Duration(seconds: 50));
        harness.gate.onBatterySample(100);
        expect(harness.notifications, isEmpty);

        harness.gate.onLinkLost();
        harness.elapse(const Duration(seconds: 20));
        harness.gate.onChargeStarted();
        expect(harness.gate.chargeStartedAt!.isAfter(firstEdge!), isTrue);
        // Time left on the old window must not finish the new one, and the
        // pre-reconnect sample is not after the new edge.
        harness.elapse(const Duration(seconds: 10));
        expect(harness.notifications, isEmpty);

        harness.elapse(const Duration(milliseconds: 1));
        harness.gate.onBatterySample(100);
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
        harness.gate.onChargeStarted();
        harness.elapse(harness.dwell + const Duration(milliseconds: 1));
        harness.gate.onBatterySample(100);
        expect(harness.notifications, [100]);

        harness.elapse(const Duration(seconds: 1));
        harness.gate.onBatterySample(66);
        harness.gate.onBatterySample(64);
        expect(harness.notifications, [100]);
        expect(harness.mismatches, [(notifiedAtLevel: 100, correctedLevel: 66)]);
        expect(harness.gate.hasAlerted, isTrue);

        harness.elapse(const Duration(seconds: 1));
        harness.gate.onBatterySample(100);
        expect(harness.notifications, [100]);
      } finally {
        harness.gate.dispose();
      }
    });
  });
}

typedef _Mismatch = ({int notifiedAtLevel, int correctedLevel});

class _Harness {
  _Harness(this.async) {
    gate = FullyChargedAlertGate(
      now: () => now,
      onFullyCharged: notifications.add,
      onLevelMismatch: ({required int notifiedAtLevel, required int correctedLevel}) {
        mismatches.add((notifiedAtLevel: notifiedAtLevel, correctedLevel: correctedLevel));
      },
    );
  }

  final FakeAsync async;
  late final FullyChargedAlertGate gate;
  final notifications = <int>[];
  final mismatches = <_Mismatch>[];
  var now = DateTime.utc(2026, 10, 11, 8);

  Duration get dwell => gate.minimumDwell;

  void elapse(Duration duration) {
    now = now.add(duration);
    async.elapse(duration);
  }
}
