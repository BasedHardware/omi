import 'dart:async';
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
import 'package:omi/pages/settings/widgets/plans/storefront_plans_content.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'storefront_plans_content_test.dart' as renders;

StorefrontTier _plan(PlanStorefront data, String planId) => data.tiers.firstWhere((tier) => tier.planId == planId);

class _Usage extends UsageProvider {
  String? checkedOutPrice;
  String? sessionPrice;
  String? upgradedPrice;
  @override
  Future<Map<String, dynamic>?> upgradeUserSubscription({required String priceId, String? promotionCode}) async {
    upgradedPrice = priceId;
    checkedOutPrice = priceId;
    return null;
  }

  @override
  Future<void> loadAvailablePlans() async {}
  @override
  Future<Map<String, dynamic>?> createUserCheckoutSession(
      {required String priceId, String? promotionCode, int? trialDays}) async {
    sessionPrice = priceId;
    checkedOutPrice = priceId;
    return null; // No browser or real payment in hermetic tests.
  }
}

class _Host extends StatefulWidget {
  const _Host(this.data, {this.gate});
  final Future<bool> Function()? gate;
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
        readStorefrontGate: widget.gate ?? () async => true,
        analyticsSource: 'budget_80',
        storefrontApi: PlanStorefrontApi(
            baseUrl: 'http://127.0.0.1:1/',
            send: (_) async => http.Response(
                File('test/fixtures/storefront_v2/plus_monthly_yearly_toggle.json').readAsStringSync(), 200)),
      ));
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });
  for (final current in ['operator', 'architect', 'legacy']) {
    testWidgets('$current subscription rejects Plus checkout even from a stale tap', (tester) async {
      tester.view.physicalSize = const Size(1000, 2200);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final usage = _Usage();
      addTearDown(usage.dispose);
      final json = jsonDecode(File('test/fixtures/storefront_v2/plus_monthly_yearly_toggle.json').readAsStringSync())
          as Map<String, dynamic>;
      json['current']['plan_id'] = current == 'legacy' ? 'unlimited_v2' : current;
      json['current']['legacy'] = current == 'legacy';
      json['current']['legacy_note'] =
          current == 'legacy' ? "We don't sell this plan anymore, but yours stays exactly as it is." : null;
      json['current']['price_id'] = 'fixture_existing';
      final data = PlanStorefront.fromJson(json);
      usage.debugSetSubscription(UserSubscriptionResponse(
        subscription: Subscription(
            plan: PlanType.fromWire(current == 'legacy' ? 'unlimited_v2' : current), status: SubscriptionStatus.active),
        transcriptionSecondsUsed: 0,
        transcriptionSecondsLimit: 0,
        wordsTranscribedUsed: 0,
        wordsTranscribedLimit: 0,
        insightsGainedUsed: 0,
        insightsGainedLimit: 0,
        availablePlans: [],
      ));
      final price = _plan(data, 'plus').priceFor('year')!;
      usage.debugSetAvailablePlans({
        'plans': [
          {
            'id': price.id,
            'plan_id': 'plus',
            'interval': 'year',
            'unit_amount': price.amountMinor,
            'title': 'Plus',
            'price_string': price.headline,
            'is_active': false
          }
        ]
      });
      await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
          value: usage,
          child: MaterialApp(
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: AppLocalizations.supportedLocales,
              home: Scaffold(body: _Host(data)))));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('storefront_buy_plus')), findsNothing);
      // Invoke the actual sheet handoff to model a tap queued before subscription refresh.
      await tester
          .widget<StorefrontPlansContent>(find.byType(StorefrontPlansContent))
          .onSelect(_plan(data, 'plus'), price);
      await tester.pumpAndSettle();
      expect(usage.checkedOutPrice, isNull);
      expect(find.text('Confirm Upgrade'), findsNothing);
      expect(find.text('Change Plan'), findsNothing);
      expect(tester.takeException(), isNull);
    });
  }
  testWidgets('architect subscription rejects Operator checkout even from a stale tap', (tester) async {
    tester.view.physicalSize = const Size(1000, 2200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final usage = _Usage();
    addTearDown(usage.dispose);
    final json = jsonDecode(File('test/fixtures/storefront_v2/plus_monthly_yearly_toggle.json').readAsStringSync())
        as Map<String, dynamic>;
    json['current']['plan_id'] = 'architect';
    json['current']['legacy'] = false;
    json['current']['price_id'] = 'fixture_architect_month';
    final data = PlanStorefront.fromJson(json);
    final price = _plan(data, 'operator').priceFor('month')!;
    usage.debugSetSubscription(UserSubscriptionResponse(
      subscription: Subscription(
          plan: PlanType.architect, status: SubscriptionStatus.active, currentPriceId: 'fixture_architect_month'),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      availablePlans: [
        SubscriptionPlan(id: 'operator', title: 'Pro', prices: [
          PricingOption(id: price.id!, title: 'Monthly', priceString: price.headline),
        ])
      ],
    ));
    usage.debugSetAvailablePlans({
      'plans': [
        {
          'id': price.id,
          'plan_id': 'operator',
          'interval': 'month',
          'unit_amount': price.amountMinor,
          'title': 'Pro',
          'price_string': price.headline,
          'is_active': false
        }
      ]
    });
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Scaffold(body: _Host(data)))));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('storefront_buy_operator')), findsNothing);
    await tester
        .widget<StorefrontPlansContent>(find.byType(StorefrontPlansContent))
        .onSelect(_plan(data, 'operator'), price);
    await tester.pumpAndSettle();
    expect(usage.checkedOutPrice, isNull);
    expect(usage.sessionPrice, isNull);
    expect(find.text('Change Plan'), findsNothing);
    expect(tester.takeException(), isNull);
  });
  testWidgets('annual subscriber has no monthly buy and a stale monthly tap does not check out', (tester) async {
    tester.view.physicalSize = const Size(1000, 2200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final usage = _Usage();
    addTearDown(usage.dispose);
    final json = jsonDecode(File('test/fixtures/storefront_v2/plus_annual_current.json').readAsStringSync())
        as Map<String, dynamic>;
    final plusTier =
        (json['tiers'] as List).cast<Map<String, dynamic>>().firstWhere((tier) => tier['plan_id'] == 'plus');
    plusTier['action'] = 'checkout';
    plusTier['cta_label'] = 'Get Plus';
    (plusTier['prices'] as List).insert(0, {
      'price_id': 'price_plus_month',
      'interval': 'month',
      'amount_minor': 1999,
      'currency': 'usd',
      'headline': r'$19.99/month',
      'subline': null,
      'renewal_line': 'Renews monthly until you cancel. Cancel anytime in settings.',
    });
    final data = PlanStorefront.fromJson(json);
    final price = _plan(data, 'plus').priceFor('month')!;
    usage.debugSetSubscription(UserSubscriptionResponse(
      subscription:
          Subscription(plan: PlanType.plus, status: SubscriptionStatus.active, currentPriceId: data.current!.priceId),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      availablePlans: [
        SubscriptionPlan(id: 'plus', title: 'Plus', prices: [
          PricingOption(id: price.id!, title: 'Monthly', priceString: price.headline),
        ])
      ],
    ));
    usage.debugSetAvailablePlans({
      'plans': [
        {
          'id': price.id,
          'plan_id': 'plus',
          'interval': 'month',
          'unit_amount': price.amountMinor,
          'title': 'Plus',
          'price_string': price.headline,
          'is_active': false
        }
      ]
    });
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Scaffold(body: _Host(data)))));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('storefront_buy_plus')), findsNothing);
    await tester
        .widget<StorefrontPlansContent>(find.byType(StorefrontPlansContent))
        .onSelect(_plan(data, 'plus'), price);
    await tester.pumpAndSettle();
    expect(usage.checkedOutPrice, isNull);
    expect(usage.sessionPrice, isNull);
    expect(find.text('Change Plan'), findsNothing);
    expect(tester.takeException(), isNull);
  });
  testWidgets('tapping Switch to yearly reaches upgrade with the yearly price', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final usage = _Usage();
    addTearDown(usage.dispose);
    final data = PlanStorefront.fromJson(
        jsonDecode(File('test/fixtures/storefront_v2/plus_monthly_yearly_toggle.json').readAsStringSync()));
    await renders.pumpSheet(tester, data: data);
    final price = _plan(data, 'plus').priceFor('year')!;
    expect(price.ctaLabel, r'Switch to yearly · save $39.98');
    expect(price.id, 'price_plus_year');
    usage.debugSetSubscription(UserSubscriptionResponse(
      subscription:
          Subscription(plan: PlanType.plus, status: SubscriptionStatus.active, currentPriceId: data.current!.priceId),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      availablePlans: [
        SubscriptionPlan(id: 'plus', title: 'Plus', prices: [
          PricingOption(id: price.id!, title: 'Yearly', priceString: price.headline),
        ])
      ],
    ));
    usage.debugSetAvailablePlans({
      'plans': [
        {
          'id': price.id,
          'plan_id': 'plus',
          'interval': 'year',
          'unit_amount': price.amountMinor,
          'title': 'Plus',
          'price_string': price.headline,
          'is_active': false
        }
      ]
    });
    await tester.pumpWidget(RepaintBoundary(
        key: renders.boundaryKey,
        child: ChangeNotifierProvider<UsageProvider>.value(
            value: usage,
            child: MaterialApp(
                debugShowCheckedModeBanner: false,
                theme: buildOmiTheme(brightness: Brightness.dark),
                localizationsDelegates: AppLocalizations.localizationsDelegates,
                supportedLocales: AppLocalizations.supportedLocales,
                home: Scaffold(body: _Host(data))))));
    await tester.pumpAndSettle();
    final button = find.text(r'Switch to yearly · save $39.98');
    await tester.ensureVisible(button);
    await tester.tap(button.hitTestable());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    for (final line in price.confirmLines) {
      expect(find.text(line), findsOneWidget);
    }
    expect(usage.upgradedPrice, isNull);
    await renders.capture(tester, '019-mobile-yearly-confirmation.png');
    await tester
        .tap(find.descendant(of: find.byType(OmiAlertDialog), matching: find.text(price.ctaLabel!)).last.hitTestable());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Change Plan'), findsNothing);
    expect(usage.upgradedPrice, price.id);
    expect(usage.sessionPrice, isNull);
    expect(tester.takeException(), isNull);
  });
  testWidgets('cancel scheduled taps only Resubscribe and it checks out the current price', (tester) async {
    tester.view.physicalSize = const Size(1000, 2200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final usage = _Usage();
    addTearDown(usage.dispose);
    final data = PlanStorefront.fromJson(
        jsonDecode(File('test/fixtures/storefront_v2/cancel_scheduled_plus.json').readAsStringSync()));
    final price = _plan(data, 'plus').priceFor('month')!;
    final pro = _plan(data, 'operator').priceFor('month')!;
    usage.debugSetSubscription(UserSubscriptionResponse(
      subscription: Subscription(
          plan: PlanType.plus, status: SubscriptionStatus.active, cancelAtPeriodEnd: true, currentPriceId: price.id),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      availablePlans: [
        SubscriptionPlan(id: 'plus', title: 'Plus', prices: [
          PricingOption(id: price.id!, title: 'Monthly', priceString: price.headline),
        ]),
        SubscriptionPlan(id: 'operator', title: 'Pro', prices: [
          PricingOption(id: pro.id!, title: 'Monthly', priceString: pro.headline),
        ]),
      ],
    ));
    usage.debugSetAvailablePlans({
      'plans': [
        {
          'id': price.id,
          'plan_id': 'plus',
          'interval': 'month',
          'unit_amount': price.amountMinor,
          'title': 'Plus',
          'price_string': price.headline,
          'is_active': true
        },
        {
          'id': pro.id,
          'plan_id': 'operator',
          'interval': 'month',
          'unit_amount': pro.amountMinor,
          'title': 'Pro',
          'price_string': pro.headline,
          'is_active': false
        },
        {
          'id': 'fixture_plus_year',
          'plan_id': 'plus',
          'interval': 'year',
          'unit_amount': 19990,
          'title': 'Plus',
          'price_string': r'$16.66/month',
          'is_active': false
        }
      ]
    });
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Scaffold(body: _Host(data)))));
    await tester.pumpAndSettle();
    expect(find.text('Upgrade to Pro'), findsNothing);
    expect(find.textContaining('Switch to yearly'), findsNothing);
    expect(find.byKey(const Key('storefront_year')), findsNothing);
    final buys = find.byWidgetPredicate((widget) {
      final key = widget.key;
      return key is ValueKey<String> && key.value.startsWith('storefront_buy_');
    });
    expect(buys, findsOneWidget);
    expect(find.byKey(const Key('storefront_buy_plus')), findsOneWidget);
    expect(find.text('Resubscribe'), findsOneWidget);
    await tester
        .widget<StorefrontPlansContent>(find.byType(StorefrontPlansContent))
        .onSelect(_plan(data, 'operator'), pro);
    await tester.pumpAndSettle();
    expect(usage.sessionPrice, isNull);
    expect(usage.upgradedPrice, isNull);
    await tester.ensureVisible(find.byKey(const Key('storefront_buy_plus')));
    await tester.tap(buys.hitTestable());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    // Resubscribe is the action. It must not ask the reader to confirm a plan change.
    expect(find.text('Change Plan'), findsNothing);
    expect(usage.sessionPrice, price.id);
    expect(usage.checkedOutPrice, price.id);
    expect(usage.upgradedPrice, isNull);
    expect(tester.takeException(), isNull);
  });
  testWidgets('payload cancel resubscribes through checkout when UsageProvider is still active', (tester) async {
    tester.view.physicalSize = const Size(1000, 2200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final usage = _Usage();
    addTearDown(usage.dispose);
    final data = PlanStorefront.fromJson(
        jsonDecode(File('test/fixtures/storefront_v2/cancel_scheduled_plus.json').readAsStringSync()));
    final price = _plan(data, 'plus').priceFor('month')!;
    expect(data.current!.cancelAtPeriodEnd, isTrue);
    usage.debugSetSubscription(UserSubscriptionResponse(
      subscription: Subscription(
          plan: PlanType.plus, status: SubscriptionStatus.active, cancelAtPeriodEnd: false, currentPriceId: price.id),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      availablePlans: [
        SubscriptionPlan(id: 'plus', title: 'Plus', prices: [
          PricingOption(id: price.id!, title: 'Monthly', priceString: price.headline),
        ]),
      ],
    ));
    usage.debugSetAvailablePlans({
      'plans': [
        {
          'id': price.id,
          'plan_id': 'plus',
          'interval': 'month',
          'unit_amount': price.amountMinor,
          'title': 'Plus',
          'price_string': price.headline,
          'is_active': true
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
    expect(find.text('Resubscribe'), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('storefront_buy_plus')));
    await tester.tap(find.byKey(const Key('storefront_buy_plus')).hitTestable());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('Change Plan').hitTestable());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(usage.sessionPrice, price.id);
    expect(usage.upgradedPrice, isNull);
    expect(tester.takeException(), isNull);
  });
  testWidgets('transcription usage legacy does not check out from the sheet', (tester) async {
    tester.view.physicalSize = const Size(1000, 2200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final usage = _Usage();
    addTearDown(usage.dispose);
    final json = jsonDecode(File('test/fixtures/storefront_v2/plus_monthly_yearly_toggle.json').readAsStringSync())
        as Map<String, dynamic>;
    json['usage']['kind'] = 'transcription';
    final data = PlanStorefront.fromJson(json);
    final price = _plan(data, 'operator').priceFor('month')!;
    usage.debugSetSubscription(UserSubscriptionResponse(
      subscription:
          Subscription(plan: PlanType.plus, status: SubscriptionStatus.active, currentPriceId: 'fixture_plus_month'),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      availablePlans: [
        SubscriptionPlan(id: 'operator', title: 'Pro', prices: [
          PricingOption(id: price.id!, title: 'Monthly', priceString: price.headline),
        ])
      ],
    ));
    usage.debugSetAvailablePlans({
      'plans': [
        {
          'id': price.id,
          'plan_id': 'operator',
          'interval': 'month',
          'unit_amount': price.amountMinor,
          'title': 'Pro',
          'price_string': price.headline,
          'is_active': false
        }
      ]
    });
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Scaffold(body: _Host(data)))));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('storefront_buy_operator')), findsNothing);
    await tester
        .widget<StorefrontPlansContent>(find.byType(StorefrontPlansContent))
        .onSelect(_plan(data, 'operator'), price);
    await tester.pumpAndSettle();
    expect(usage.sessionPrice, isNull);
    expect(usage.upgradedPrice, isNull);
    expect(find.text('Change Plan'), findsNothing);
    expect(tester.takeException(), isNull);
  });
  testWidgets('flag off keeps Plans & Billing and the storefront flag uses Plans', (tester) async {
    late BuildContext sheetContext;
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Builder(builder: (context) {
        sheetContext = context;
        return const SizedBox.shrink();
      }),
    ));
    expect(await plansSheetTitle(sheetContext, sheetEnabled: () async => false), 'Plans & Billing');
    expect(await plansSheetTitle(sheetContext, sheetEnabled: () async => true), 'Plans');
  });
  testWidgets('pending storefront gate does not check out live unlimited', (tester) async {
    tester.view.physicalSize = const Size(1000, 2200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final usage = _Usage();
    addTearDown(usage.dispose);
    final pending = Completer<bool>();
    final data = PlanStorefront.fromJson(
        jsonDecode(File('test/fixtures/storefront_v2/plus_monthly_yearly_toggle.json').readAsStringSync()));
    usage.debugSetSubscription(UserSubscriptionResponse(
      subscription: Subscription(
          plan: PlanType.unlimitedV2, status: SubscriptionStatus.active, stripeSubscriptionId: 'sub_fixture'),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      availablePlans: [
        SubscriptionPlan(id: 'plus', title: 'Plus', prices: [
          PricingOption(id: 'fixture_plus_year', title: 'Yearly', priceString: r'$199.90'),
        ])
      ],
    ));
    usage.debugSetAvailablePlans({
      'plans': [
        {
          'id': 'fixture_unlimited_month',
          'plan_id': 'unlimited_v2',
          'interval': 'month',
          'unit_amount': 1999,
          'title': 'Unlimited',
          'price_string': r'$19.99',
          'is_active': true
        },
        {
          'id': 'fixture_plus_year',
          'plan_id': 'plus',
          'interval': 'year',
          'unit_amount': 19990,
          'title': 'Plus',
          'price_string': r'$199.90',
          'is_active': false
        }
      ]
    });
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Scaffold(body: _Host(data, gate: () => pending.future)))));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.byType(StorefrontPlansContent), findsNothing);
    final button = find.byKey(const ValueKey('plans_sheet_upgrade_button'));
    await tester.scrollUntilVisible(button, 200, scrollable: find.byType(Scrollable).first);
    await tester.tap(button.hitTestable());
    await tester.pumpAndSettle();
    expect(usage.checkedOutPrice, isNull);
    expect(usage.sessionPrice, isNull);
    expect(find.byType(OmiAlertDialog), findsNothing);
    pending.complete(false);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
  testWidgets('unresolved storefront flag paints existing plans sheet', (tester) async {
    final usage = _Usage();
    addTearDown(usage.dispose);
    final pending = Completer<bool>();
    final data = PlanStorefront.fromJson(
        jsonDecode(File('test/fixtures/storefront_v2/plus_monthly_yearly_toggle.json').readAsStringSync()));
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
        value: usage,
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Scaffold(body: _Host(data, gate: () => pending.future)))));
    await tester.pump();
    expect(find.byType(StorefrontPlansContent), findsNothing);
    expect(find.byType(OmiLoadingState), findsNothing);
    pending.complete(false);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
  for (final mismatch in ['none', 'id', 'amount', 'interval']) {
    testWidgets('existing checkout receives exact storefront price only when mismatch=$mismatch', (tester) async {
      tester.view.physicalSize = const Size(1000, 2200);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final usage = _Usage();
      addTearDown(usage.dispose);
      final json = jsonDecode(File('test/fixtures/storefront_v2/plus_monthly_yearly_toggle.json').readAsStringSync())
          as Map<String, dynamic>;
      json['current'] = null;
      final plusTier =
          (json['tiers'] as List).cast<Map<String, dynamic>>().firstWhere((tier) => tier['plan_id'] == 'plus');
      plusTier['is_current'] = false;
      plusTier['action'] = 'checkout';
      plusTier['cta_label'] = 'Get Plus';
      (plusTier['prices'] as List).insert(0, {
        'price_id': 'price_plus_month',
        'interval': 'month',
        'amount_minor': 1999,
        'currency': 'usd',
        'headline': r'$19.99/month',
        'subline': null,
        'renewal_line': 'Renews monthly until you cancel. Cancel anytime in settings.',
      });
      final data = PlanStorefront.fromJson(json);
      final price = _plan(data, 'plus').priceFor('month')!;
      final catalogId = mismatch == 'id' ? 'fixture_different_price' : price.id!;
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
            PricingOption(id: catalogId, title: 'Monthly', priceString: price.headline),
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
            'unit_amount': mismatch == 'amount' ? price.amountMinor + 1 : price.amountMinor,
            'price_string': price.headline,
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
      await tester.ensureVisible(find.byKey(const Key('storefront_other_plans')));
      await tester.tap(find.byKey(const Key('storefront_other_plans')).hitTestable());
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.byKey(const Key('storefront_buy_plus')));
      await tester.tap(find.byKey(const Key('storefront_buy_plus')).hitTestable());
      await tester.pumpAndSettle();
      expect(usage.checkedOutPrice, mismatch == 'none' ? price.id : isNull);
      expect(tester.takeException(), isNull);
    });
  }
}
