/// The moments at which a reading surface may ask the operating system for a
/// review. The caller is responsible for calling [recordEngagement] only after
/// valid reading content has loaded.
enum AppReviewMoment {
  dailySummaryRead,
  conversationRead,
}

/// Closed decisions emitted by the review opportunity telemetry.
enum AppReviewDecision {
  eligible,
  notIosOrAndroid,
  storageError,
  notFamiliar,
  migrationCooldown,
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
        AppReviewDecision.notFamiliar => 'not_familiar',
        AppReviewDecision.migrationCooldown => 'migration_cooldown',
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
  static const int minimumReadingDays = 3;
  static const Duration minimumElapsedSinceFirstReading = Duration(days: 7);
  static const Duration requestCooldown = Duration(days: 120);
  static const Duration rollingAttemptWindow = Duration(days: 365);
  static const int maximumAttemptsInWindow = 3;

  /// The history is deliberately bounded. Three calls per rolling year means
  /// this retains more than twenty years of normal operation while avoiding an
  /// unbounded preference value if a future caller misbehaves.
  static const int maximumStoredAttempts = 64;

  /// Distinct day keys are enough to establish familiarity; raw reading data
  /// must never enter this state.
  static const int maximumStoredReadingDays = 32;

  static AppReviewDecision evaluate({
    required String platform,
    required String appVersion,
    required DateTime now,
    required DateTime? firstSeen,
    required int distinctReadingDays,
    required Iterable<AppReviewAttempt> attempts,
    required DateTime? migratedAt,
    required bool attemptedThisSession,
  }) {
    if (platform != 'ios' && platform != 'android') {
      return AppReviewDecision.notIosOrAndroid;
    }
    if (attemptedThisSession) {
      return AppReviewDecision.sessionAlreadyAttempted;
    }
    if (migratedAt != null && now.difference(migratedAt) < requestCooldown) {
      return AppReviewDecision.migrationCooldown;
    }
    if (firstSeen == null ||
        distinctReadingDays < minimumReadingDays ||
        now.difference(firstSeen) < minimumElapsedSinceFirstReading) {
      return AppReviewDecision.notFamiliar;
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
    if (latestAttempt != null && now.difference(latestAttempt.at) < requestCooldown) {
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
