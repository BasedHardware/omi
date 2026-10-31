import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

/// Re-offers the plans to free users when they open the app (A/B, flag `paywall-reask`).
///
/// Readers who don't pay keep opening Omi but rarely meet a paywall, because every other paywall
/// waits for a limit. The re-ask comes back on app open, spaced out so it never nags: 2, 3, 5
/// and then every 7 days, counted from the last paywall the reader saw anywhere (so a limit or a
/// Settings upgrade restarts the clock) and, for someone who never saw one, from their first Home
/// visit (never on onboarding day).
///
/// Each due moment is an exposure for both arms (control is the denominator); control advances the
/// same schedule without showing anything, so both arms are counted at the same moments.
/// Fail-closed: no identity, an unread flag or any error shows nothing and exposes no one.
/// Pre-registration: `app/lib/services/experiments/paywall_reask.md`.
abstract final class PaywallReask {
  /// PostHog flag key (project 302298). Registered in `config/feature-flags.yaml`.
  static const enabledFlag = 'paywall-reask';

  /// [PromptQueue] id for the queued re-ask.
  static const promptId = 'paywall-reask';

  /// Days between re-asks; the last gap repeats.
  static const gapsInDays = [2, 3, 5, 7];

  /// Variants of the flag that show the re-ask; `control` and anything else show nothing.
  static const treatmentVariants = {'test', 'treatment', 'reask'};

  /// Debug override: `--dart-define=OMI_PAYWALL_REASK=test` (or `=control`). With
  /// `OMI_PAYWALL_REASK_NOW=true` the re-ask is due on every launch, for trying it on a simulator.
  static const _debugVariant = String.fromEnvironment('OMI_PAYWALL_REASK');
  static const _debugAlwaysDue = bool.fromEnvironment('OMI_PAYWALL_REASK_NOW');

  static String _lastShownKey(String uid) => 'paywall/lastShownAt/$uid';
  static String _countKey(String uid) => 'paywall/reaskCount/$uid';

  /// The gap before the next re-ask after [reasksSoFar] of them.
  static int gapAfter(int reasksSoFar) => gapsInDays[reasksSoFar.clamp(0, gapsInDays.length - 1)];

  /// Whole local calendar days from [from] to [to].
  static int daysBetween(DateTime from, DateTime to) =>
      (DateTime(to.year, to.month, to.day).difference(DateTime(from.year, from.month, from.day)).inHours / 24).round();

  /// True when a re-ask is due: at least the scheduled gap since the last paywall.
  static bool isDue({required DateTime now, required DateTime lastShown, required int reasksSoFar}) =>
      daysBetween(lastShown, now) >= gapAfter(reasksSoFar);

  /// A paywall was shown (any source): restarts the clock.
  static void noteShown({DateTime? now}) {
    final uid = SharedPreferencesUtil().uid;
    if (uid.isEmpty) return;
    SharedPreferencesUtil().saveInt(_lastShownKey(uid), (now ?? DateTime.now()).millisecondsSinceEpoch);
  }

  /// Called on Home open for a free reader. Returns true when the treatment arm should show the
  /// re-ask now; records the exposure and advances the schedule for both arms. [readVariant] and
  /// [recordExposure] default to the analytics manager and are injectable for tests.
  static Future<bool> checkDue({
    DateTime? now,
    Future<String?> Function(String key)? readVariant,
    bool Function(String key, String variant)? recordExposure,
  }) async {
    final prefs = SharedPreferencesUtil();
    final uid = prefs.uid;
    if (uid.isEmpty) return false;
    final at = now ?? DateTime.now();
    final lastMs = prefs.getInt(_lastShownKey(uid), defaultValue: 0);
    if (lastMs == 0) {
      // First Home visit without any paywall yet: start the clock, never ask today.
      noteShown(now: at);
      if (!(kDebugMode && _debugAlwaysDue)) return false;
    }
    final count = prefs.getInt(_countKey(uid), defaultValue: 0);
    final last = DateTime.fromMillisecondsSinceEpoch(lastMs == 0 ? at.millisecondsSinceEpoch : lastMs);
    if (!(kDebugMode && _debugAlwaysDue) && !isDue(now: at, lastShown: last, reasksSoFar: count)) return false;

    final String? variant;
    if (kDebugMode && _debugVariant.isNotEmpty) {
      variant = _debugVariant;
    } else {
      try {
        variant = await (readVariant ?? AnalyticsManager().getFeatureFlagVariant)(enabledFlag);
      } catch (_) {
        return false;
      }
    }
    if (variant == null || variant.trim().isEmpty) return false; // not in the experiment
    (recordExposure ?? AnalyticsManager().recordFeatureFlagExposure)(enabledFlag, variant.trim());
    prefs.saveInt(_countKey(uid), count + 1);
    noteShown(now: at);
    return treatmentVariants.contains(variant.trim().toLowerCase());
  }
}
