// Local plan catalog for tests and the demo walk. Production billing is [UsageProvider]'s real
// payment calls. Nothing here is referenced from lib/, and the walk opts in by passing
// [demoAuditProviders] as the suite roster.
import 'package:nested/nested.dart';

import 'package:omi/models/subscription.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/providers/usage_provider.dart';

import 'fakes.dart';

/// Free-plan reader with a two-tier catalog. Checkout and plan refresh do not call the network
/// or StoreKit; they leave this snapshot in place.
class DemoBillingUsage extends UsageProvider {
  DemoBillingUsage()
      : super(
          deviceTimeZone: () async => 'America/Chicago',
          subscriptionRequest: () async => demoFreeSubscription,
          usageRequest: ({required period, required timeZone}) async => UserUsageResponse(
            today: demoUsageStats,
            monthly: demoUsageStats,
            yearly: demoUsageStats,
            allTime: demoUsageStats,
            history: const [],
          ),
        ) {
    debugSetSubscription(demoFreeSubscription);
    debugSetAvailablePlans(demoPlanCatalog);
    debugSetUsage('today', demoUsageStats, const []);
    debugSetUsage('monthly', demoUsageStats, const []);
    debugSetUsage('yearly', demoUsageStats, const []);
    debugSetUsage('all_time', demoUsageStats, const []);
  }

  @override
  Future<void> loadAvailablePlans() async {}

  @override
  Future<void> fetchSubscription() async {}

  @override
  Future<void> fetchUsageStats({required String period}) async {}

  @override
  Future<Map<String, dynamic>?> upgradeUserSubscription({required String priceId, String? promotionCode}) async => null;

  @override
  Future<Map<String, dynamic>?> createUserCheckoutSession({
    required String priceId,
    String? promotionCode,
    int? trialDays,
  }) async =>
      null;

  @override
  Future<bool> cancelUserSubscription({String? reason, String? reasonDetails}) async => false;
}

/// The default audit roster with [DemoBillingUsage] in place of the real payment provider.
List<SingleChildWidget> demoAuditProviders() => defaultAuditProviders(usage: DemoBillingUsage.new);

final demoUsageStats = UsageStats(
  transcriptionSeconds: 2400,
  speechSeconds: 1800,
  wordsTranscribed: 4200,
  insightsGained: 6,
  memoriesCreated: 3,
);

final demoFreeSubscription = UserSubscriptionResponse(
  subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
  transcriptionSecondsUsed: 2400,
  transcriptionSecondsLimit: 7200,
  wordsTranscribedUsed: 900,
  wordsTranscribedLimit: 0,
  insightsGainedUsed: 4,
  insightsGainedLimit: 0,
  showSubscriptionUi: true,
  // A trial-eligible reader can be sent to the trial page instead of the plans sheet.
  trialEligible: false,
  availablePlans: [
    SubscriptionPlan(id: 'unlimited_v2', title: 'Omi Pro', features: ['Unlimited conversations', 'Ask Omi anything']),
    SubscriptionPlan(id: 'plus', title: 'Plus', features: ['More transcription']),
  ],
);

/// Same shape the plans sheet already renders in widget tests. Amounts are the catalog the sheet
/// formats; they are not a live price and nothing here can be purchased.
final demoPlanCatalog = <String, dynamic>{
  'plans': <dynamic>[
    _price('plus', 'Plus', 'month', 1999),
    _price('plus', 'Plus', 'year', 17990),
    _price('unlimited_v2', 'Unlimited', 'month', 2999),
    _price('unlimited_v2', 'Unlimited', 'year', 23990),
  ],
};

Map<String, dynamic> _price(String planId, String title, String interval, int amount) => {
      'id': 'price_${planId}_$interval',
      'plan_id': planId,
      'title': title,
      'interval': interval,
      'unit_amount': amount,
      'currency': 'usd',
      'is_active': false,
    };
