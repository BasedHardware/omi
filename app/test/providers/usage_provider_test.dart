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
}
