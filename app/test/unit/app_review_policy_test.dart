import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/app_review_policy.dart';

void main() {
  final now = DateTime(2026, 9, 22, 12);

  AppReviewDecision evaluate({
    String platform = 'ios',
    String version = '1.2',
    DateTime? firstSeen,
    int days = 3,
    Iterable<AppReviewAttempt> attempts = const [],
    DateTime? migratedAt,
    bool session = false,
  }) {
    return AppReviewPolicy.evaluate(
      platform: platform,
      appVersion: version,
      now: now,
      firstSeen: firstSeen ?? now.subtract(const Duration(days: 7)),
      distinctReadingDays: days,
      attempts: attempts,
      migratedAt: migratedAt,
      attemptedThisSession: session,
    );
  }

  test('requires a supported mobile platform and familiar reading history', () {
    expect(evaluate(platform: 'macos'), AppReviewDecision.notIosOrAndroid);
    expect(evaluate(days: 2), AppReviewDecision.notFamiliar);
    expect(evaluate(firstSeen: now.subtract(const Duration(days: 6))), AppReviewDecision.notFamiliar);
  });

  test('enforces migration cooldown, session, version, spacing, and budget', () {
    expect(
      evaluate(migratedAt: now.subtract(const Duration(days: 119))),
      AppReviewDecision.migrationCooldown,
    );
    expect(evaluate(session: true), AppReviewDecision.sessionAlreadyAttempted);
    expect(
      evaluate(attempts: [AppReviewAttempt(at: now.subtract(const Duration(days: 365)), version: '1.2')]),
      AppReviewDecision.versionAlreadyAttempted,
    );
    expect(
      evaluate(attempts: [AppReviewAttempt(at: now.subtract(const Duration(days: 1)), version: '1.1')]),
      AppReviewDecision.cooldown,
    );
    expect(
      evaluate(
        attempts: [
          AppReviewAttempt(at: now.subtract(const Duration(days: 1)), version: '1.0'),
          AppReviewAttempt(at: now.subtract(const Duration(days: 121)), version: '1.1'),
          AppReviewAttempt(at: now.subtract(const Duration(days: 240)), version: '1.2.1'),
        ],
      ),
      AppReviewDecision.budgetExhausted,
    );
  });

  test('allows the exact cooldown and rolling-window boundaries', () {
    expect(
      evaluate(attempts: [AppReviewAttempt(at: now.subtract(const Duration(days: 120)), version: '1.1')]),
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
  });
}
