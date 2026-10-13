import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/plan_storefront_api.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class _Usage extends UsageProvider {
  String? checkedOutPrice;
  @override
  Future<void> loadAvailablePlans() async {}
  @override
  Future<Map<String, dynamic>?> createUserCheckoutSession({required String priceId, String? promotionCode}) async {
    checkedOutPrice = priceId;
    return null; // No browser or real payment in hermetic tests.
  }
}

class _Host extends StatefulWidget {
  const _Host(this.data);
  final PlanStorefront data;
  @override
  State<_Host> createState() => _HostState();
}

class _HostState extends State<_Host> with TickerProviderStateMixin {
  late final animation = AnimationController(vsync: this);
  @override
  void dispose() {
    animation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => OmiSheetScaffold(
          child: PlansSheet(
        waveController: animation,
        notesController: animation,
        arrowController: animation,
        arrowAnimation: animation,
        initialStorefront: widget.data,
        readStorefrontGate: () async => true,
        analyticsSource: 'budget_80_percent',
        storefrontApi: PlanStorefrontApi(
            baseUrl: 'http://127.0.0.1:1/',
            send: (_) async => http.Response(File('test/fixtures/plan_storefront.json').readAsStringSync(), 200)),
      ));
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });
  for (final mismatch in ['none', 'id', 'amount', 'interval']) {
    testWidgets('existing checkout receives exact storefront price only when mismatch=$mismatch', (tester) async {
      tester.view.physicalSize = const Size(430, 2200);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final usage = _Usage();
      addTearDown(usage.dispose);
      final json = jsonDecode(File('test/fixtures/plan_storefront.json').readAsStringSync()) as Map<String, dynamic>;
      json['current'] = null;
      final data = PlanStorefront.fromJson(json);
      final price = data.tiers[1].priceFor('month')!;
      final catalogId = mismatch == 'id' ? 'fixture_different_price' : price.id;
      usage.debugSetSubscription(UserSubscriptionResponse(
        subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.inactive),
        transcriptionSecondsUsed: 0,
        transcriptionSecondsLimit: 0,
        wordsTranscribedUsed: 0,
        wordsTranscribedLimit: 0,
        insightsGainedUsed: 0,
        insightsGainedLimit: 0,
        availablePlans: [
          SubscriptionPlan(id: 'plus', title: 'Plus', prices: [
            PricingOption(id: catalogId, title: 'Monthly', priceString: price.formatted),
          ])
        ],
      ));
      usage.debugSetAvailablePlans({
        'plans': [
          {
            'id': catalogId,
            'plan_id': 'plus',
            'title': 'Plus',
            'interval': mismatch == 'interval' ? 'year' : 'month',
            'unit_amount': mismatch == 'amount' ? price.amount + 1 : price.amount,
            'price_string': price.formatted,
            'is_active': false
          },
        ]
      });
      await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
          value: usage,
          child: MaterialApp(
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: AppLocalizations.supportedLocales,
              home: Scaffold(body: _Host(data)))));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('storefront_buy_plus')));
      await tester.pumpAndSettle();
      expect(usage.checkedOutPrice, mismatch == 'none' ? price.id : isNull);
      expect(tester.takeException(), isNull);
    });
  }
}
