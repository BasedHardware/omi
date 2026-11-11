import 'package:flutter_test/flutter_test.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/models/transcription_allowance.dart';
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
    phoneCallQuota: PhoneCallQuota(hasAccess: true, isPaid: true),
  );
}

UserSubscriptionResponse _subscriptionOn(PlanType plan,
    {required int used,
    required int limit,
    String? mode = 'managed',
    String reason = 'plan_within_allowance',
    bool? phoneAccess = false}) {
  return UserSubscriptionResponse(
    subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
    transcriptionSecondsUsed: used,
    transcriptionSecondsLimit: limit,
    wordsTranscribedUsed: 0,
    wordsTranscribedLimit: 0,
    insightsGainedUsed: 0,
    insightsGainedLimit: 0,
    phoneCallQuota: phoneAccess == null ? null : PhoneCallQuota(hasAccess: phoneAccess, isPaid: false),
    transcriptionAllowance: mode == null ? null : TranscriptionAllowanceSnapshot(mode: mode, reason: reason),
  );
}

void main() {
  test('older servers without an allowance retain counter-based credit gating', () {
    final provider = UsageProvider();
    addTearDown(provider.dispose);
    for (final plan in [PlanType.basic, PlanType.plus]) {
      for (final used in [299, 300, 301]) {
        provider.debugSetSubscription(_subscriptionOn(plan, used: used, limit: 300, mode: null));
        expect(provider.subscription!.transcriptionAllowance, isNull);
        expect(provider.isOutOfCredits, used >= 300, reason: '${plan.name}: $used/300');
      }
      provider.debugSetSubscription(_subscriptionOn(plan, used: 300, limit: 0, mode: null));
      expect(provider.isOutOfCredits, isFalse, reason: 'zero is an unlimited limit');
    }
    for (final plan in [PlanType.unlimited, PlanType.unlimitedV2, PlanType.operator]) {
      provider.debugSetSubscription(_subscriptionOn(plan, used: 301, limit: 300, mode: null));
      expect(provider.isOutOfCredits, isFalse, reason: '${plan.name} has unlimited transcription');
    }
  });

  test('older servers without phone quota retain paid-plan access', () {
    final provider = UsageProvider();
    addTearDown(provider.dispose);
    for (final entry in {
      PlanType.basic: false,
      PlanType.plus: true,
      PlanType.unlimitedV2: true,
      PlanType.unknown('future_plan'): false,
    }.entries) {
      provider.debugSetSubscription(_subscriptionOn(entry.key, used: 0, limit: 0, phoneAccess: null));
      expect(provider.phoneCallQuota, isNull);
      expect(provider.canAccessPhoneCalls, entry.value, reason: entry.key.name);
    }
  });

  test('exhausted ladder budget overrides the Pro unlimited-transcription shortcut', () {
    final provider = UsageProvider();
    provider.debugSetSubscription(UserSubscriptionResponse(
      subscription: Subscription(plan: PlanType.operator, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      transcriptionAllowance: const TranscriptionAllowanceSnapshot(
          mode: 'on_device', reason: 'usage_budget_exhausted', remainingSeconds: 0),
    ));
    expect(provider.isOutOfCredits, true);
  });
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
      provider.debugSetSubscription(_subscriptionOn(PlanType.plus,
          used: 90000, limit: 90000, mode: 'on_device', reason: 'plan_allowance_exhausted'));
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
        provider.debugSetSubscription(_subscriptionOn(plan, used: 0, limit: 0, phoneAccess: true));
        expect(provider.canAccessPhoneCalls, isTrue, reason: '${plan.name} is paid');
      }
    });

    test('an unknown plan does not unlock paid-only features', () {
      final provider = UsageProvider();
      provider.debugSetSubscription(_subscriptionOn(PlanType.unknown('future_plan_123'), used: 0, limit: 0));

      expect(provider.canAccessPhoneCalls, isFalse);
    });
  });
  test('server mode wins over contradictory local counters and plan labels', () {
    final provider = UsageProvider();
    for (final plan in [PlanType.basic, PlanType.plus, PlanType.operator]) {
      for (final mode in ['managed', 'on_device', 'blocked']) {
        provider.debugSetSubscription(
            _subscriptionOn(plan, used: 999999, limit: 1, mode: mode, reason: 'plan_allowance_exhausted'));
        expect(provider.isOutOfCredits, mode != 'managed');
      }
    }
  });

  test('transient server refusal does not advertise exhausted credits', () {
    final provider = UsageProvider();
    for (final reason in ['allowance_unavailable', 'usage_invalid']) {
      provider.debugSetSubscription(
          _subscriptionOn(PlanType.plus, used: 999999, limit: 1, mode: 'on_device', reason: reason));
      expect(provider.isOutOfCredits, false);
    }
  });

  test('phone-call admission always uses the server has_access answer', () {
    final provider = UsageProvider();
    for (final plan in [PlanType.basic, PlanType.plus, PlanType.operator]) {
      for (final access in [false, true]) {
        provider.debugSetSubscription(_subscriptionOn(plan, used: 0, limit: 0, phoneAccess: access));
        expect(provider.canAccessPhoneCalls, access);
      }
    }
    provider.debugSetSubscription(null);
    expect(provider.canAccessPhoneCalls, false);
    expect(provider.isOutOfCredits, false);
  });
}
