import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/experiments/pendant_reconnect_nudge.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

void main() {
  final now = DateTime(2026, 11, 27, 12);
  final today = PendantReconnectNudge.localDay(now);

  PendantReconnectNudgeEligible? decide({
    bool enabled = true,
    String uid = 'fixture-1',
    bool paired = true,
    Duration? gap = const Duration(days: 4),
    Duration? sinceShown,
    Duration? sinceEnrolled,
    String otherSurfaceDay = '',
    DateTime? syncAlertAt,
  }) =>
      PendantReconnectNudge.evaluate(
        enabled: enabled,
        uid: uid,
        hasPairedPendant: paired,
        now: now,
        lastConnectedAt: gap == null ? 0 : now.subtract(gap).millisecondsSinceEpoch,
        lastShownAt: sinceShown == null ? 0 : now.subtract(sinceShown).millisecondsSinceEpoch,
        lastEnrolledAt: sinceEnrolled == null ? 0 : now.subtract(sinceEnrolled).millisecondsSinceEpoch,
        lastDropoffSurfaceDay: otherSurfaceDay,
        lastSyncAlertAt: syncAlertAt?.millisecondsSinceEpoch ?? 0,
        createdAt: now.subtract(const Duration(days: 14)),
        paying: true,
      );

  test('fixed SHA-256 fixtures keep their assigned halves', () {
    const treatment = [1, 2, 3, 4, 5, 8, 10, 279];
    const holdout = [0, 6, 7, 9, 11, 15, 17, 185];
    for (final fixture in treatment) {
      expect(PendantReconnectNudge.armFor('fixture-$fixture'), PendantReconnectNudgeEligibleArm.treatment);
    }
    for (final fixture in holdout) {
      expect(PendantReconnectNudge.armFor('fixture-$fixture'), PendantReconnectNudgeEligibleArm.holdout);
    }
  });

  test('holdout still enrolls with the same eligibility properties', () {
    expect(decide(uid: 'fixture-0')?.properties, {
      'arm': 'holdout',
      'days_since_connection': 'days_3_to_6',
      'tenure_days': 'days_14_to_59',
      'paying': 'paying',
    });
  });

  test('the switch, auth, pendant, and connection evidence are required', () {
    expect(decide(enabled: false), isNull);
    expect(decide(uid: ''), isNull);
    expect(decide(paired: false), isNull);
    expect(decide(gap: null), isNull);
    expect(decide(gap: const Duration(days: -1)), isNull);
  });

  test('eligibility starts exactly at 72 hours', () {
    expect(decide(gap: const Duration(hours: 72) - const Duration(milliseconds: 1)), isNull);
    expect(decide(gap: const Duration(hours: 72))?.arm, PendantReconnectNudgeEligibleArm.treatment);
  });

  test('the cap expires after 30 full days', () {
    expect(decide(sinceShown: const Duration(days: 30) - const Duration(milliseconds: 1)), isNull);
    expect(decide(sinceShown: const Duration(days: 30)), isNotNull);
  });

  test('the same enrollment window expires after 30 full days for either arm', () {
    for (final uid in ['fixture-0', 'fixture-1']) {
      expect(decide(uid: uid, sinceEnrolled: const Duration(days: 29, hours: 23)), isNull);
      expect(decide(uid: uid, sinceEnrolled: const Duration(days: 30)), isNotNull);
    }
  });

  test('the drop-off and sync-stall surfaces suppress only on the same local day', () {
    final yesterday = DateTime(2026, 11, 26, 23, 59);
    expect(decide(otherSurfaceDay: today), isNull);
    expect(decide(otherSurfaceDay: PendantReconnectNudge.localDay(yesterday)), isNotNull);
    expect(decide(syncAlertAt: DateTime(2026, 11, 27).toUtc()), isNull);
    expect(decide(syncAlertAt: yesterday), isNotNull);
  });

  test('the duration bands change at 7, 14 and 30 days', () {
    for (final (days, bucket) in [
      (6, 'days_3_to_6'),
      (7, 'days_7_to_13'),
      (14, 'days_14_to_29'),
      (30, 'days_30_plus')
    ]) {
      expect(decide(gap: Duration(days: days))?.properties['days_since_connection'], bucket);
    }
  });
}
