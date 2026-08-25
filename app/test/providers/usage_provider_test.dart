import 'package:flutter_test/flutter_test.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/providers/usage_provider.dart';

UserSubscriptionResponse _proSubscription() {
  return UserSubscriptionResponse(
    subscription: Subscription(plan: PlanType.unlimited, status: SubscriptionStatus.active),
    transcriptionSecondsUsed: 0,
    transcriptionSecondsLimit: 0,
    wordsTranscribedUsed: 0,
    wordsTranscribedLimit: 0,
    insightsGainedUsed: 0,
    insightsGainedLimit: 0,
  );
}

UserSubscriptionResponse _subscriptionOn(PlanType plan, {required int used, required int limit}) {
  return UserSubscriptionResponse(
    subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
    transcriptionSecondsUsed: used,
    transcriptionSecondsLimit: limit,
    wordsTranscribedUsed: 0,
    wordsTranscribedLimit: 0,
    insightsGainedUsed: 0,
    insightsGainedLimit: 0,
  );
}

void main() {
  group('UsageProvider.clearUserData', () {
    test('resets subscription state so the next login cannot inherit the previous account plan', () {
      final provider = UsageProvider();
      provider.debugSetSubscription(_proSubscription());
      expect(provider.subscription, isNotNull);
      expect(provider.canAccessPhoneCalls, isTrue);

      var notified = false;
      provider.addListener(() => notified = true);
      provider.clearUserData();

      expect(provider.subscription, isNull);
      expect(provider.canAccessPhoneCalls, isFalse);
      expect(provider.isOutOfCredits, isFalse);
      expect(provider.error, isNull);
      expect(notified, isTrue);
    });
  });

  group('UsageProvider credit gating across tiers', () {
    test('Plus is metered: running out of transcription seconds blocks capture', () {
      // Plus is a paid plan but capped at 1500 min/month, so it must NOT be
      // treated as unlimited the way Neo/Operator/Architect/Unlimited are.
      final provider = UsageProvider();
      provider.debugSetSubscription(_subscriptionOn(PlanType.plus, used: 90000, limit: 90000));
      expect(provider.isOutOfCredits, isTrue);

      provider.debugSetSubscription(_subscriptionOn(PlanType.plus, used: 100, limit: 90000));
      expect(provider.isOutOfCredits, isFalse);
    });

    test('Unlimited (v2) never runs out of credits', () {
      final provider = UsageProvider();
      provider.debugSetSubscription(_subscriptionOn(PlanType.unlimitedV2, used: 999999, limit: 0));
      expect(provider.isOutOfCredits, isFalse);
    });

    test('paid mobile tiers unlock paid-only features', () {
      final provider = UsageProvider();
      for (final plan in [PlanType.plus, PlanType.unlimitedV2]) {
        provider.debugSetSubscription(_subscriptionOn(plan, used: 0, limit: 0));
        expect(provider.canAccessPhoneCalls, isTrue, reason: '${plan.name} is paid');
      }
    });
  });
}
