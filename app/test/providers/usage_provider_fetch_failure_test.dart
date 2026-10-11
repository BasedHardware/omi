import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/providers/usage_provider.dart';

class _UnreachableApiEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    Env.init(_UnreachableApiEnv());
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('a failed subscription refresh keeps the plan that was already loaded', () async {
    final provider = UsageProvider();
    provider.debugSetSubscription(
      UserSubscriptionResponse(
        subscription: Subscription(plan: PlanType.unlimited, status: SubscriptionStatus.active),
        transcriptionSecondsUsed: 0,
        transcriptionSecondsLimit: 0,
        wordsTranscribedUsed: 0,
        wordsTranscribedLimit: 0,
        insightsGainedUsed: 0,
        insightsGainedLimit: 0,
      ),
    );

    await provider.fetchSubscription();

    expect(provider.subscription?.subscription.plan, PlanType.unlimited);
    expect(provider.canAccessPhoneCalls, isTrue);
    expect(provider.isLoading, isFalse);
    expect(provider.error, isNotNull);
  });
}
