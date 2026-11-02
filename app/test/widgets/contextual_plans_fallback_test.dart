import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/plans/contextual_plans.dart';
import 'package:omi/pages/settings/widgets/plans/plan_cards.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

Map<String, dynamic> _price(String planId, String title, String interval, int amount) => {
      'id': 'price_${planId}_$interval',
      'plan_id': planId,
      'title': title,
      'interval': interval,
      'unit_amount': amount,
      'price_string': '\$${amount ~/ 100}/${interval == 'year' ? 'yr' : 'mo'}',
      'is_active': false,
    };

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  // The held-audio "Processing paused" Upgrade button calls this. With the storefront flag off it
  // used to return false and the button did nothing.
  testWidgets('Upgrade opens the plans sheet when the storefront flag is off', (tester) async {
    await tester.binding.setSurfaceSize(const Size(430, 2400));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final usage = UsageProvider();
    addTearDown(usage.dispose);
    usage.debugSetSubscription(
      UserSubscriptionResponse(
        subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
        transcriptionSecondsUsed: 0,
        transcriptionSecondsLimit: 0,
        wordsTranscribedUsed: 0,
        wordsTranscribedLimit: 0,
        insightsGainedUsed: 0,
        insightsGainedLimit: 0,
      ),
    );
    usage.debugSetAvailablePlans({
      'plans': <dynamic>[
        _price('unlimited_v2', 'Unlimited', 'month', 1900),
        _price('unlimited_v2', 'Unlimited', 'year', 19000),
      ]
    });

    bool? opened;
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<UsageProvider>.value(value: usage),
          ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: Scaffold(
            body: Builder(
              builder: (context) => TextButton(
                onPressed: () async =>
                    opened = await openContextualPlans(context, source: 'held_audio', trigger: 'usage_budget'),
                child: const Text('Upgrade'),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Upgrade'));
    for (var i = 0; i < 20; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(find.byType(PlansSheet), findsOneWidget);
    expect(find.byType(PlanOptionCard), findsNWidgets(2));
    expect(find.text('US\$19.00/month'), findsOneWidget);
    Navigator.of(tester.element(find.byType(PlansSheet))).pop();
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(opened, isTrue);
  });
}
