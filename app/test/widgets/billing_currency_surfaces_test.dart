import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/gen/payments_wire.g.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/pages/paywall/outline_paywall_page.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/pages/paywall/trial_paywall_page.dart';
import 'package:omi/pages/paywall/trial_upsell_sheet.dart';
import 'package:omi/pages/paywall/web_paywall_page.dart';
import 'package:omi/pages/settings/widgets/cancel_subscription_sheet.dart';
import 'package:omi/pages/settings/widgets/plans/plan_cards.dart';
import 'package:omi/pages/settings/widgets/plans/storefront_plans_content.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/billing_price.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../helpers/sfpro_font_fixtures.dart';

const _evidence = String.fromEnvironment('OMI_BILLING_EVIDENCE_DIR');
const _boundary = Key('billing_evidence');
const _offer = PaywallOffer(
  tierId: 'unlimited_v2',
  monthly: PaywallPrice(priceId: 'price_fixture_month', interval: 'month', amountMinor: 2999, currency: 'usd'),
  yearly: PaywallPrice(priceId: 'price_fixture_year', interval: 'year', amountMinor: 26991, currency: 'usd'),
);

Map<String, dynamic> _row(PaywallPrice price) => {
      'id': price.priceId,
      'plan_id': 'unlimited_v2',
      'title': 'Omi Pro',
      'interval': price.interval,
      'unit_amount': price.amountMinor,
      'currency': price.currency,
      // Poisoned preformatted fields must never reach purchase presentation.
      'price_string': 'WRONG CAD 999',
      'billing_total': 'WRONG CAD 999',
    };

class _Usage extends UsageProvider {
  _Usage() : super(deviceTimeZone: () async => 'UTC');

  final sessions = <(String, int?, String?)>[];
  @override
  Future<void> fetchSubscription() async {}
  @override
  Future<void> loadAvailablePlans() async {}
  @override
  Future<Map<String, dynamic>?> createUserCheckoutSession(
      {required String priceId, String? promotionCode, int? trialDays}) async {
    sessions.add((priceId, trialDays, promotionCode));
    return {'error': true, 'status_code': 400, 'detail': 'Fixture: checkout handoff captured'};
  }
}

_Usage _usage({bool jpy = false}) {
  final usage = _Usage();
  usage.debugSetSubscription(UserSubscriptionResponse(
    subscription: Subscription(
      plan: jpy ? PlanType.plus : PlanType.basic,
      status: SubscriptionStatus.active,
      stripeSubscriptionId: jpy ? 'sub_fixture' : null,
      currentPeriodEnd: DateTime.utc(2026, 11, 28).millisecondsSinceEpoch ~/ 1000,
    ),
    trialEligible: true,
    transcriptionSecondsUsed: 0,
    transcriptionSecondsLimit: 18000,
    wordsTranscribedUsed: 0,
    wordsTranscribedLimit: 0,
    insightsGainedUsed: 0,
    insightsGainedLimit: 0,
  ));
  usage.debugSetAvailablePlans({
    'plans': [_row(_offer.yearly!), _row(_offer.monthly!)]
  });
  return usage;
}

class _Plans extends StatefulWidget {
  const _Plans();
  @override
  State<_Plans> createState() => _PlansState();
}

class _PlansState extends State<_Plans> with SingleTickerProviderStateMixin {
  late final _animation = AnimationController(vsync: this);
  @override
  void dispose() {
    _animation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => PlansSheet(
      waveController: _animation, notesController: _animation, arrowController: _animation, arrowAnimation: _animation);
}

Future<void> _capture(WidgetTester tester, String name) async {
  if (_evidence.isEmpty || !(name.contains('en_US') || name.contains('en_CA'))) return;
  await tester.pump();
  await tester.runAsync(() async {
    final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(_boundary));
    final image = await boundary.toImage(pixelRatio: 2);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(_evidence).create(recursive: true);
    await File('$_evidence/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

Future<void> _pump(WidgetTester tester, Locale locale, _Usage usage, Widget page,
    {Size size = const Size(430, 1000), bool settle = true}) async {
  final previousPalette = OmiColors.active;
  OmiColors.active = OmiPalette.dark;
  addTearDown(() => OmiColors.active = previousPalette);
  Intl.defaultLocale = locale.toString();
  addTearDown(() => Intl.defaultLocale = null);
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  if (_evidence.isNotEmpty) {
    await tester.runAsync(() async {
      final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
      for (final entry in manifest) {
        final loader = FontLoader(entry['family'] as String);
        for (final font in entry['fonts'] as List) {
          loader.addFont(rootBundle.load(font['asset'] as String));
        }
        await loader.load();
      }
      for (final family in [
        'Roboto',
        'FlutterTest',
        '.SF UI Text',
        '.SF UI Display',
        'CupertinoSystemText',
        'CupertinoSystemDisplay'
      ]) {
        await (FontLoader(family)..addFont(sfProFont('SFPRODISPLAYREGULAR.OTF'))).load();
      }
    });
  }
  await tester.pumpWidget(RepaintBoundary(
      key: _boundary,
      child: MultiProvider(
        providers: [
          ChangeNotifierProvider<UsageProvider>.value(value: usage),
          ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
        ],
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          locale: locale,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          theme: buildOmiTheme(brightness: Brightness.dark).copyWith(platform: TargetPlatform.android),
          home: Scaffold(body: page),
        ),
      )));
  if (settle) {
    await tester.pumpAndSettle();
  } else {
    await tester.pump(const Duration(milliseconds: 400));
  }
  expect(tester.takeException(), isNull);
}

Future<void> _tap(WidgetTester tester, Finder finder) async {
  if (finder.evaluate().isEmpty) {
    final vertical =
        find.byWidgetPredicate((widget) => widget is Scrollable && widget.axisDirection == AxisDirection.down);
    await tester.scrollUntilVisible(finder, 200, scrollable: vertical.first);
  }
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  for (final locale in [
    const Locale('en', 'US'),
    const Locale('en', 'CA'),
    const Locale('en', 'IN'),
    const Locale('de', 'DE')
  ]) {
    final tag = locale.toString();
    for (final capped in [true, false]) {
      testWidgets('$tag chat compute usage uses the shared USD formatter (capped=$capped)', (tester) async {
        final usage = _usage();
        await usage.refreshUsageTimeZone();
        usage.debugSetSubscription(UserSubscriptionResponse(
          subscription: Subscription(
              plan: PlanType.unlimitedV2,
              status: SubscriptionStatus.active,
              limits: PlanLimits(chatCostUsdPerMonth: capped ? 80 : null)),
          transcriptionSecondsUsed: 0,
          transcriptionSecondsLimit: 0,
          wordsTranscribedUsed: 0,
          wordsTranscribedLimit: 0,
          insightsGainedUsed: 0,
          insightsGainedLimit: 0,
          chatQuotaUnit: 'cost_usd',
          chatQuotaUsed: 18.25,
        ));
        final zero = UsageStats(
            transcriptionSeconds: 0, speechSeconds: 0, wordsTranscribed: 0, insightsGained: 0, memoriesCreated: 0);
        usage.debugSetUsage('today', zero, []);
        usage.debugSetUsage('monthly', zero, []);
        await _pump(tester, locale, usage, const UsagePage(debugSkipFetch: true),
            size: const Size(430, 1200), settle: false);
        final l10n = AppLocalizations.of(tester.element(find.byType(UsagePage)));
        await tester.tap(find.text(l10n.usageMonth));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 400));
        final expected = capped ? r'US$18.25 / US$80.00' : r'US$18.25';
        await tester.scrollUntilVisible(find.text(expected), 200,
            scrollable: find
                .descendant(of: find.byKey(const Key('usage_scroll_monthly')), matching: find.byType(Scrollable))
                .first);
        await tester.pump();
        expect(find.text(expected), findsOneWidget);
        expect(l10n.chatUsageCost(r'US$18.25', r'US$80.00'), contains(r'US$18.25'));
        expect(l10n.chatUsageCostNoLimit(r'US$18.25'), isNot(contains(r'$US$')));
        expect(l10n.chatUsedOfLimitCompute(r'US$18.25', r'US$80.00'), isNot(contains(r'$US$')));
        await _capture(tester, '${tag}_chat_usage_${capped ? 'capped' : 'uncapped'}');
      });
    }
    testWidgets('$tag trial card, post-trial disclosure and real checkout handoff agree', (tester) async {
      final usage = _usage();
      await _pump(
          tester, locale, usage, TrialPaywallPage(source: 'onboarding', offer: _offer, now: DateTime(2026, 10, 28)));
      await _capture(tester, '${tag}_trial_slide_1');
      for (var i = 2; i <= 5; i++) {
        await tester.drag(find.byType(PageView), const Offset(-430, 0));
        await tester.pumpAndSettle();
        await _capture(tester, '${tag}_trial_slide_$i');
      }
      final l10n = AppLocalizations.of(tester.element(find.byType(TrialPaywallPage)));
      for (final price in [_offer.monthly!, _offer.yearly!]) {
        final card = find.byKey(Key('trial_paywall_${price.interval == 'year' ? 'yearly' : 'monthly'}'));
        await _tap(tester, card);
        expect(find.descendant(of: card, matching: find.text(price.formatted)), findsOneWidget);
        expect(find.text(l10n.billingTrialPrice(7, price.formatted, price.interval)), findsWidgets);
        expect(price.formatted, price.interval == 'year' ? r'US$269.91' : r'US$29.99');
        await _capture(tester, '${tag}_trial_${price.interval}_card');
        await _tap(tester, find.byKey(const Key('trial_paywall_cta')));
        expect(usage.sessions.last, (price.priceId, 7, null));
        await tester.pump(const Duration(seconds: 9));
        await tester.pumpAndSettle();
      }
      expect(find.textContaining('WRONG'), findsNothing);
    });

    testWidgets('$tag outline and hosted-web bridge use the identical USD strings', (tester) async {
      PaywallPrice? selected;
      await _pump(
          tester,
          locale,
          _usage(),
          OutlinePaywallPage(
              source: 'usage_page',
              offer: _offer,
              checkout: (_, price, __) async {
                selected = price;
                return PaywallCheckoutOutcome.cancelled;
              }));
      expect(find.text(r'US$269.91'), findsOneWidget);
      expect(find.text(r'US$29.99'), findsNWidgets(2));
      await _capture(tester, '${tag}_outline');
      await _tap(tester, find.byKey(const Key('outline_paywall_cta')));
      expect(selected?.priceId, _offer.yearly!.priceId);
      final url = WebPaywallPage.buildUrl(Uri.parse('https://example.invalid/paywall'),
          source: 'usage_page',
          platform: 'android',
          locale: locale.toLanguageTag(),
          name: '',
          freeMinutes: 300,
          offer: _offer);
      expect(url.queryParameters['year_price'], r'US$269.91');
      expect(url.queryParameters['month_price'], r'US$29.99');
    });

    testWidgets('$tag 30-day trial upsell discloses the checkout price', (tester) async {
      PaywallPrice? selected;
      await _pump(
          tester,
          locale,
          _usage(),
          Align(
              alignment: Alignment.bottomCenter,
              child: TrialUpsellContent(
                  source: 'onboarding',
                  offer: _offer,
                  price: _offer.yearly!,
                  checkout: (_, price, __) async {
                    selected = price;
                    return PaywallCheckoutOutcome.cancelled;
                  })));
      expect(find.textContaining(r'US$269.91'), findsOneWidget);
      await _capture(tester, '${tag}_trial_upsell');
      await _tap(tester, find.byKey(const Key('trial_upsell_claim')));
      expect(selected?.formatted, r'US$269.91');
    });

    testWidgets('$tag plans and promo redemption use catalog numbers, never price_string', (tester) async {
      final usage = _usage();
      await _pump(tester, locale, usage, const _Plans(), size: const Size(430, 1200));
      expect(find.textContaining('WRONG'), findsNothing);
      expect(find.textContaining(r'US$269.91'), findsWidgets);
      expect(find.textContaining(r'US$29.99'), findsWidgets);
      await _capture(tester, '${tag}_plans');
      final l10n = AppLocalizations.of(tester.element(find.byType(PlansSheet)));
      await _tap(tester, find.text(l10n.promoCode));
      await tester.enterText(find.byType(TextField), 'FIXTURE_PROMO');
      await tester.pump();
      await _capture(tester, '${tag}_promo');
      await _tap(tester, find.byKey(const Key('plans_sheet_upgrade_button')));
      expect(usage.sessions.last, (_offer.yearly!.priceId, null, 'FIXTURE_PROMO'));
    });

    testWidgets('$tag V2 paid cards show the exact recurring checkout total', (tester) async {
      final data = PlanStorefront.fromJson(
          jsonDecode(File('test/fixtures/storefront_v2/single_plan_omi_pro.json').readAsStringSync())
              as Map<String, dynamic>);
      StorefrontPrice? selected;
      await _pump(
          tester,
          locale,
          _usage(),
          StorefrontPlansContent(
              storefront: data,
              onRetry: () async {},
              onSelect: (_, price) async {
                selected = price;
              },
              onManage: () async {}));
      expect(find.textContaining(r'US$29.99'), findsOneWidget);
      await _capture(tester, '${tag}_v2_plans_month');
      await _tap(tester, find.byKey(const Key('storefront_year')));
      expect(find.textContaining(r'US$269.91'), findsWidgets);
      await _capture(tester, '${tag}_v2_plans_year');
      await _tap(tester, find.byKey(const Key('storefront_buy_unlimited_v2')));
      expect(selected?.amountMinor, 26991);
      expect(selected?.currency, 'usd');
    });

    testWidgets('$tag retention offer uses the same formatter', (tester) async {
      await _pump(
          tester,
          locale,
          _usage(),
          CancelSubscriptionFlow(
              loadOffer: () async => GeneratedRetentionOfferResponse.fromJson({
                    'eligible': true,
                    'percent_off': 50,
                    'duration_months': 3,
                    'discounted_amount': 1500,
                    'currency': 'usd'
                  })));
      final l10n = AppLocalizations.of(tester.element(find.byType(CancelSubscriptionFlow)));
      await _tap(tester, find.text(l10n.cancelReasonTooExpensive));
      await _tap(tester, find.text(l10n.continueButton));
      await _tap(tester, find.text(l10n.continueButton));
      expect(find.textContaining(r'US$15.00'), findsOneWidget);
      await _capture(tester, '${tag}_retention');
    });
  }

  for (final locale in [const Locale('en', 'US'), const Locale('en', 'CA')]) {
    testWidgets('$locale legacy JPY management keeps whole yen and the selected price ID', (tester) async {
      final usage = _usage(jpy: true);
      const monthly =
          PaywallPrice(priceId: 'price_jpy_fixture_month', interval: 'month', amountMinor: 4800, currency: 'jpy');
      const yearly =
          PaywallPrice(priceId: 'price_jpy_fixture_year', interval: 'year', amountMinor: 43200, currency: 'jpy');
      usage.debugSetAvailablePlans({
        'plans': [_row(yearly), _row(monthly)]
      });
      await _pump(tester, locale, usage, const _Plans(), size: const Size(430, 1200));
      expect(find.textContaining('¥43,200'), findsWidgets);
      expect(find.textContaining('¥4,800'), findsWidgets);
      expect(find.textContaining('US\$'), findsNothing);
      await _capture(tester, '${locale}_jpy_manage');
      await _tap(tester, find.widgetWithText(PlanOptionCard, 'Omi Pro · Monthly'));
      await tester.tap(find.byKey(const Key('plans_sheet_upgrade_button')));
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.textContaining('¥4,800'), findsWidgets);
      expect(usage.sessions, isEmpty, reason: 'existing subscription management must confirm before mutation');
    });

    testWidgets('$locale V2 JPY current line formats raw catalog yen and ignores stale formatted text', (tester) async {
      final json =
          jsonDecode(File('test/fixtures/storefront_v2/legacy_neo.json').readAsStringSync()) as Map<String, dynamic>;
      final current = json['current'] as Map<String, dynamic>;
      current.addAll({
        'amount_minor': 4800,
        'currency': 'jpy',
        'line': 'WRONG USD',
        'line_template': "You're on Neo · {price}/mo · renews Nov 1"
      });
      final data = PlanStorefront.fromJson(json);
      await _pump(
          tester,
          locale,
          _usage(jpy: true),
          StorefrontPlansContent(
              storefront: data, onRetry: () async {}, onSelect: (_, __) async {}, onManage: () async {}));
      expect(find.textContaining('¥4,800'), findsOneWidget);
      expect(find.textContaining('WRONG'), findsNothing);
      await _capture(tester, '${locale}_jpy_v2_manage');
    });
  }

  test('V2 price templates use raw minor amounts for offers and confirmations', () {
    final price = StorefrontPrice.fromJson({
      'price_id': 'price_fixture_year',
      'interval': 'year',
      'amount_minor': 26991,
      'currency': 'usd',
      'headline': 'WRONG',
      'cta_label': 'WRONG',
      'confirm_lines': ['WRONG'],
      'cta_label_template': 'Save {saving}',
      'saving_minor': 8997,
      'confirm_line_templates': ['Then {price} per year']
    });
    expect(price.formattedCtaLabel, r'Save US$89.97');
    expect(price.formattedConfirmLines, [r'Then US$269.91 per year']);
  });

  test('ISO-safe symbols and Stripe minor-unit exponents', () {
    expect(formatBillingPrice(2999, 'usd'), r'US$29.99');
    expect(formatBillingPrice(0, 'usd'), r'US$0.00');
    expect(formatBillingPrice(4800, 'jpy'), '¥4,800');
    expect(formatBillingPrice(2999, 'cad'), 'CAD 29.99');
    expect(formatBillingPrice(1234, 'kwd'), 'KWD 1.234');
    expect(formatBillingPrice(500, 'isk'), 'ISK 5.00');
  });
}
