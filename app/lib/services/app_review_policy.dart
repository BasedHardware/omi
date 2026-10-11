/// The moments at which a reading surface may ask the operating system for a
/// review. The caller admits only loaded, valid reading content.
enum AppReviewMoment { dailySummaryRead, conversationRead }

/// Closed decisions emitted by the review opportunity telemetry.
enum AppReviewDecision {
  eligible,
  notIosOrAndroid,
  storageError,
  recentBadExperience,
  cooldown,
  budgetExhausted,
  versionAlreadyAttempted,
  sessionAlreadyAttempted,
  lifecycleNotAppropriate,
  lifecycleChanged,
  availabilityError,
  unavailable,
  requestError,
}

extension AppReviewMomentName on AppReviewMoment {
  String get telemetryName => switch (this) {
        AppReviewMoment.dailySummaryRead => 'daily_summary_read',
        AppReviewMoment.conversationRead => 'conversation_read',
      };
}

extension AppReviewDecisionName on AppReviewDecision {
  String get telemetryName => switch (this) {
        AppReviewDecision.eligible => 'eligible',
        AppReviewDecision.notIosOrAndroid => 'not_ios_or_android',
        AppReviewDecision.storageError => 'storage_error',
        AppReviewDecision.recentBadExperience => 'recent_bad_experience',
        AppReviewDecision.cooldown => 'cooldown',
        AppReviewDecision.budgetExhausted => 'budget_exhausted',
        AppReviewDecision.versionAlreadyAttempted => 'version_already_attempted',
        AppReviewDecision.sessionAlreadyAttempted => 'session_already_attempted',
        AppReviewDecision.lifecycleNotAppropriate => 'lifecycle_not_appropriate',
        AppReviewDecision.lifecycleChanged => 'lifecycle_changed',
        AppReviewDecision.availabilityError => 'availability_error',
        AppReviewDecision.unavailable => 'unavailable',
        AppReviewDecision.requestError => 'request_error',
      };
}

/// Tunable hypotheses for when review requests are useful and respectful.
///
/// The operating systems still apply their own display limits. These local
/// limits prevent us from repeatedly entering that system prompt path and give
/// us a stable surface for future telemetry-informed tuning.
abstract final class AppReviewPolicy {
  static const Duration requestCooldown = Duration(days: 30);
  static const Duration badExperienceWindow = Duration(days: 3);
  static const Duration rollingAttemptWindow = Duration(days: 365);
  static const int maximumAttemptsInWindow = 3;

  /// The history is deliberately bounded. Three calls per rolling year means
  /// this retains more than twenty years of normal operation while avoiding an
  /// unbounded preference value if a future caller misbehaves.
  static const int maximumStoredAttempts = 64;

  static AppReviewDecision evaluate({
    required String platform,
    required String appVersion,
    required DateTime now,
    required Iterable<AppReviewAttempt> attempts,
    required Iterable<DateTime> badExperiences,
    required bool attemptedThisSession,
    Duration cooldown = requestCooldown,
  }) {
    if (platform != 'ios' && platform != 'android') {
      return AppReviewDecision.notIosOrAndroid;
    }
    if (attemptedThisSession) {
      return AppReviewDecision.sessionAlreadyAttempted;
    }
    if (badExperiences.any((at) => now.difference(at) < badExperienceWindow)) {
      return AppReviewDecision.recentBadExperience;
    }
    if (appVersion.isEmpty) {
      return AppReviewDecision.storageError;
    }

    final attemptList = attempts.toList(growable: false);
    final cutoff = now.subtract(rollingAttemptWindow);
    final recentAttempts = attemptList.where((attempt) => !attempt.at.isBefore(cutoff));
    if (recentAttempts.length >= maximumAttemptsInWindow) {
      return AppReviewDecision.budgetExhausted;
    }
    if (attemptList.any((attempt) => attempt.version == appVersion)) {
      return AppReviewDecision.versionAlreadyAttempted;
    }

    final latestAttempt = attemptList.isEmpty ? null : attemptList.reduce((a, b) => a.at.isAfter(b.at) ? a : b);
    if (latestAttempt != null && now.difference(latestAttempt.at) < cooldown) {
      return AppReviewDecision.cooldown;
    }
    return AppReviewDecision.eligible;
  }
}

/// Internal value passed to [AppReviewPolicy]. It intentionally contains only
/// timestamps and the app version, never a conversation or user identifier.
final class AppReviewAttempt {
  const AppReviewAttempt({required this.at, required this.version});

  final DateTime at;
  final String version;
}
