import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/services/wals/sync_rate_limit_reconciliation.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:shared_preferences/shared_preferences.dart';

UserSubscriptionResponse _subscriptionResponse({
  required PlanType plan,
  SubscriptionStatus status = SubscriptionStatus.active,
}) {
  return UserSubscriptionResponse(
    subscription: Subscription(plan: plan, status: status),
    transcriptionSecondsUsed: 0,
    transcriptionSecondsLimit: 0,
    wordsTranscribedUsed: 0,
    wordsTranscribedLimit: 0,
    insightsGainedUsed: 0,
    insightsGainedLimit: 0,
  );
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();
  });

  test('clears stale rate limit when subscription refresh confirms active operator plan', () {
    SyncRateLimiter.instance.markLimited(retryAfterSeconds: 3600);
    expect(SyncRateLimiter.instance.isLimited, isTrue);

    reconcileSyncRateLimitWithSubscription(_subscriptionResponse(plan: PlanType.operator));

    expect(SyncRateLimiter.instance.isLimited, isFalse);
  });

  test('keeps active rate limit for basic subscription', () {
    SyncRateLimiter.instance.markLimited(retryAfterSeconds: 3600);

    reconcileSyncRateLimitWithSubscription(_subscriptionResponse(plan: PlanType.basic));

    expect(SyncRateLimiter.instance.isLimited, isTrue);
  });

  test('keeps active rate limit for inactive paid subscription', () {
    SyncRateLimiter.instance.markLimited(retryAfterSeconds: 3600);

    reconcileSyncRateLimitWithSubscription(
      _subscriptionResponse(plan: PlanType.operator, status: SubscriptionStatus.inactive),
    );

    expect(SyncRateLimiter.instance.isLimited, isTrue);
  });

  test('clears stale rate limit when fair-use status is unrestricted', () {
    SyncRateLimiter.instance.markLimited(retryAfterSeconds: 3600);
    expect(SyncRateLimiter.instance.isLimited, isTrue);

    reconcileSyncRateLimitWithFairUseStatus({'stage': 'none'});

    expect(SyncRateLimiter.instance.isLimited, isFalse);
  });

  test('keeps active rate limit when fair-use status is still restricted', () {
    SyncRateLimiter.instance.markLimited(retryAfterSeconds: 3600);

    reconcileSyncRateLimitWithFairUseStatus({'stage': 'restrict'});

    expect(SyncRateLimiter.instance.isLimited, isTrue);
  });
}
