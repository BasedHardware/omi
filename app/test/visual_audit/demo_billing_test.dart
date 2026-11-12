import 'package:flutter_test/flutter_test.dart';

import 'package:omi/models/subscription.dart';

import '../../integration_test/visual_audit/demo_billing.dart';

void main() {
  test('demo catalog is a free plan and does not call payment', () async {
    final usage = DemoBillingUsage();
    addTearDown(usage.dispose);

    expect(usage.subscription?.subscription.plan, PlanType.basic);
    expect(usage.subscription?.subscription.plan.isPaid, isFalse);
    expect(usage.showSubscriptionUI, isTrue);
    expect(usage.subscription?.trialEligible, isFalse);
    expect(usage.availablePlans?['plans'], isNotEmpty);
    expect(usage.todayUsage, isNotNull);
    expect(usage.error, isNull);

    await usage.loadAvailablePlans();
    await usage.fetchSubscription();
    await usage.fetchUsageStats(period: 'today');

    expect(usage.availablePlans?['plans'], isNotEmpty);
    expect(usage.subscription?.subscription.plan, PlanType.basic);
    expect(usage.error, isNull);
    expect(await usage.upgradeUserSubscription(priceId: 'price_unlimited_v2_year'), isNull);
    expect(await usage.createUserCheckoutSession(priceId: 'price_unlimited_v2_year'), isNull);
    expect(await usage.cancelUserSubscription(), isFalse);
    expect(usage.error, isNull);
  });
}
