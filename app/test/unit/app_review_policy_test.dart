import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/app_review_policy.dart';

void main() {
  final now = DateTime(2026, 9, 22, 12);

  AppReviewDecision evaluate({
    String platform = 'ios',
    String version = '1.2',
    Iterable<AppReviewAttempt> attempts = const [],
    Iterable<DateTime> badExperiences = const [],
    bool session = false,
    Duration cooldown = AppReviewPolicy.requestCooldown,
  }) {
    return AppReviewPolicy.evaluate(
      platform: platform,
      appVersion: version,
      now: now,
      attempts: attempts,
      badExperiences: badExperiences,
      attemptedThisSession: session,
      cooldown: cooldown,
    );
  }

  test('requires a supported mobile platform, with no familiarity gate', () {
    expect(evaluate(platform: 'macos'), AppReviewDecision.notIosOrAndroid);
    expect(evaluate(), AppReviewDecision.eligible);
  });

  test('enforces bad experience, session, version, spacing, and budget', () {
    expect(evaluate(badExperiences: [now.subtract(const Duration(days: 2))]), AppReviewDecision.recentBadExperience);
    expect(evaluate(badExperiences: [now.subtract(const Duration(days: 3))]), AppReviewDecision.eligible);
    expect(evaluate(session: true), AppReviewDecision.sessionAlreadyAttempted);
    expect(
      evaluate(
        attempts: [AppReviewAttempt(at: now.subtract(const Duration(days: 365)), version: '1.2')],
      ),
      AppReviewDecision.versionAlreadyAttempted,
    );
    expect(
      evaluate(
        attempts: [AppReviewAttempt(at: now.subtract(const Duration(days: 1)), version: '1.1')],
      ),
      AppReviewDecision.cooldown,
    );
    expect(
      evaluate(
        attempts: [
          AppReviewAttempt(at: now.subtract(const Duration(days: 1)), version: '1.0'),
          AppReviewAttempt(at: now.subtract(const Duration(days: 31)), version: '1.1'),
          AppReviewAttempt(at: now.subtract(const Duration(days: 240)), version: '1.2.1'),
        ],
      ),
      AppReviewDecision.budgetExhausted,
    );
  });

  test('allows the exact cooldown and rolling-window boundaries', () {
    expect(
      evaluate(
        attempts: [AppReviewAttempt(at: now.subtract(const Duration(days: 30)), version: '1.1')],
      ),
      AppReviewDecision.eligible,
    );
    expect(
      evaluate(
        attempts: [AppReviewAttempt(at: now.subtract(const Duration(days: 29)), version: '1.1')],
      ),
      AppReviewDecision.cooldown,
    );
    expect(
      evaluate(
        attempts: [AppReviewAttempt(at: now.subtract(const Duration(days: 9)), version: '1.1')],
        cooldown: const Duration(days: 7),
      ),
      AppReviewDecision.eligible,
    );
    expect(
      evaluate(
        attempts: [
          AppReviewAttempt(at: now.subtract(const Duration(days: 365)), version: '1.3'),
          AppReviewAttempt(at: now.subtract(const Duration(days: 364)), version: '1.4'),
          AppReviewAttempt(at: now.subtract(const Duration(days: 240)), version: '1.5'),
        ],
      ),
      AppReviewDecision.budgetExhausted,
    );
  });

  test('uses closed telemetry names', () {
    expect(AppReviewMoment.dailySummaryRead.telemetryName, 'daily_summary_read');
    expect(AppReviewMoment.conversationRead.telemetryName, 'conversation_read');
    expect(AppReviewDecision.requestError.telemetryName, 'request_error');
    expect(AppReviewDecision.recentBadExperience.telemetryName, 'recent_bad_experience');
  });
}
