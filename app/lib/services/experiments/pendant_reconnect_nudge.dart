// Owns EXP-005 assignment and eligibility. The flag must resolve on before
// the client evaluates an account, and only bucketed context leaves this decision.
import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';

import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

abstract final class PendantReconnectNudge {
  static const enabledFlag = 'pendant-reconnect-nudge';
  static const _salt = 'EXP-005-pendant-reconnect-nudge:';

  // Mobile's existing flag path reads the authenticated Omi flag store.
  // A failed refresh can leave a cached true, so use the cache only after success.
  static Future<bool> readFlag(String uid) async {
    final auth = AuthService.instance;
    final session = auth.captureSessionSnapshot(expectedUid: uid);
    if (session == null || AnalyticsManager.currentIdentity != uid) return false;
    final analytics = AnalyticsManager();
    return await analytics.reloadFeatureFlags() &&
        auth.isSessionSnapshotCurrent(session) &&
        AnalyticsManager.currentIdentity == uid &&
        analytics.isBooleanFeatureEnabledCached(enabledFlag);
  }

  static String localDay(DateTime time) => time.toLocal().toIso8601String().split('T').first;

  static PendantReconnectNudgeEligibleArm armFor(String uid) =>
      sha256.convert(utf8.encode('$_salt$uid')).bytes.first < 128
          ? PendantReconnectNudgeEligibleArm.treatment
          : PendantReconnectNudgeEligibleArm.holdout;

  static PendantReconnectNudgeEligible? evaluate({
    required bool enabled,
    required String uid,
    required bool hasPairedPendant,
    required DateTime now,
    required int lastConnectedAt,
    required int lastShownAt,
    required int lastEnrolledAt,
    required String lastDropoffSurfaceDay,
    required int lastSyncAlertAt,
    required DateTime? createdAt,
    required bool? paying,
  }) {
    if (!enabled || uid.isEmpty || !hasPairedPendant || lastConnectedAt <= 0) return null;

    final gap = now.difference(DateTime.fromMillisecondsSinceEpoch(lastConnectedAt));
    if (gap < const Duration(hours: 72)) return null;
    final cooldownStartedAt = max(lastShownAt, lastEnrolledAt);
    if (cooldownStartedAt > 0 &&
        now.difference(DateTime.fromMillisecondsSinceEpoch(cooldownStartedAt)) < const Duration(days: 30)) {
      return null;
    }

    final today = localDay(now);
    if (lastDropoffSurfaceDay == today ||
        (lastSyncAlertAt > 0 && localDay(DateTime.fromMillisecondsSinceEpoch(lastSyncAlertAt)) == today)) {
      return null;
    }

    return PendantReconnectNudgeEligible(
      arm: armFor(uid),
      daysSinceConnection: switch (gap.inDays) {
        < 7 => PendantReconnectNudgeEligibleDaysSinceConnection.days3To6,
        < 14 => PendantReconnectNudgeEligibleDaysSinceConnection.days7To13,
        < 30 => PendantReconnectNudgeEligibleDaysSinceConnection.days14To29,
        _ => PendantReconnectNudgeEligibleDaysSinceConnection.days30Plus,
      },
      tenureDays: switch (createdAt == null ? null : now.difference(createdAt).inDays) {
        null => PendantReconnectNudgeEligibleTenureDays.unknown,
        < 14 => PendantReconnectNudgeEligibleTenureDays.under14,
        < 60 => PendantReconnectNudgeEligibleTenureDays.days14To59,
        _ => PendantReconnectNudgeEligibleTenureDays.days60Plus,
      },
      paying: switch (paying) {
        true => PendantReconnectNudgeEligiblePaying.paying,
        false => PendantReconnectNudgeEligiblePaying.notPaying,
        null => PendantReconnectNudgeEligiblePaying.unknown,
      },
    );
  }
}

extension PendantReconnectNudgeEvents on PendantReconnectNudgeEligible {
  PendantReconnectNudgeShown get shown => PendantReconnectNudgeShown(
        arm: PendantReconnectNudgeShownArm.treatment,
        daysSinceConnection: PendantReconnectNudgeShownDaysSinceConnection.values.byName(daysSinceConnection.name),
        tenureDays: PendantReconnectNudgeShownTenureDays.values.byName(tenureDays.name),
        paying: PendantReconnectNudgeShownPaying.values.byName(paying.name),
      );

  PendantReconnectNudgeTapped get tapped => PendantReconnectNudgeTapped(
        arm: PendantReconnectNudgeTappedArm.treatment,
        daysSinceConnection: PendantReconnectNudgeTappedDaysSinceConnection.values.byName(daysSinceConnection.name),
        tenureDays: PendantReconnectNudgeTappedTenureDays.values.byName(tenureDays.name),
        paying: PendantReconnectNudgeTappedPaying.values.byName(paying.name),
      );

  PendantReconnectNudgeDismissed get dismissed => PendantReconnectNudgeDismissed(
        arm: PendantReconnectNudgeDismissedArm.treatment,
        daysSinceConnection: PendantReconnectNudgeDismissedDaysSinceConnection.values.byName(daysSinceConnection.name),
        tenureDays: PendantReconnectNudgeDismissedTenureDays.values.byName(tenureDays.name),
        paying: PendantReconnectNudgeDismissedPaying.values.byName(paying.name),
      );
}
