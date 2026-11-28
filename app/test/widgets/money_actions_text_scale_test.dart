import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/gen/payments_wire.g.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/pages/paywall/trial_upsell_sheet.dart';
import 'package:omi/pages/settings/widgets/cancel_subscription_sheet.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../helpers/sfpro_font_fixtures.dart';

// Cancelling, and claiming or declining the 30-day offer, must stay reachable at every text size.
// The app does not clamp the system text scale, so the largest is iOS's largest accessibility size
// (AX5), which draws 17 pt body text at 53 pt.
const _textScales = [1.0, 53 / 17];
const _iphone17Pro = Size(402, 874);
const _iphoneSE = Size(375, 667);

const _offer = PaywallOffer(
  tierId: 'unlimited_v2',
  monthly: PaywallPrice(priceId: 'price_fixture_month', interval: 'month', amountMinor: 2999, currency: 'usd'),
  yearly: PaywallPrice(priceId: 'price_fixture_year', interval: 'year', amountMinor: 26991, currency: 'usd'),
);

class _Usage extends UsageProvider {
  _Usage() : super(deviceTimeZone: () async => 'UTC');

  final cancelReasons = <String?>[];

  @override
  Future<void> fetchSubscription({bool fresh = false}) async {}

  @override
  Future<bool> cancelUserSubscription({String? reason, String? reasonDetails}) async {
    cancelReasons.add(reason);
    return true;
  }
}

_Usage _proPayer() => _Usage()
  ..debugSetSubscription(UserSubscriptionResponse(
    subscription: Subscription(
      plan: PlanType.unlimitedV2,
      status: SubscriptionStatus.active,
      stripeSubscriptionId: 'sub_fixture',
      currentPeriodEnd: DateTime.utc(2026, 12, 11).millisecondsSinceEpoch ~/ 1000,
    ),
    transcriptionSecondsUsed: 0,
    transcriptionSecondsLimit: 0,
    wordsTranscribedUsed: 0,
    wordsTranscribedLimit: 0,
    insightsGainedUsed: 0,
    insightsGainedLimit: 0,
  ));

GeneratedRetentionOfferResponse _retentionOffer() => GeneratedRetentionOfferResponse.fromJson(
    {'eligible': true, 'percent_off': 50, 'duration_months': 3, 'discounted_amount': 1500, 'currency': 'usd'});

/// An iPhone 17 Pro sized screen (or [size]) at [textScale]; returns a context to open the flow from.
Future<BuildContext> _pumpHost(WidgetTester tester, double textScale, _Usage usage,
    {Size size = _iphone17Pro, Locale locale = const Locale('en')}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  tester.view.padding = size == _iphoneSE ? const FakeViewPadding(top: 20) : const FakeViewPadding(top: 62, bottom: 34);
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  late BuildContext home;
  await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
    value: usage,
    child: MaterialApp(
      locale: locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: buildOmiTheme(brightness: Brightness.light),
      home: Builder(builder: (context) {
        home = context;
        return const Scaffold(body: SizedBox.expand());
      }),
    ),
  ));
  return home;
}

/// On screen and hit by a tap at its centre, without scrolling first.
void _expectReachable(Finder finder) => expect(finder.hitTestable(), findsOneWidget);

Finder _button(String label) => find.widgetWithText(OmiButton, label);

/// SF Pro instead of the square test glyphs, so line breaks match an iPhone. Scripts SF Pro lacks
/// (Arabic) still draw as full-width squares, which only makes their lines longer.
Future<void> _loadSfPro(WidgetTester tester) => tester.runAsync(() async {
      for (final family in ['.SF UI Text', '.SF Pro Text', 'SF Pro Display', 'CupertinoSystemText', 'FlutterTest']) {
        final loader = FontLoader(family);
        for (final weight in ['REGULAR', 'MEDIUM', 'BOLD']) {
          loader.addFont(sfProFont('SFPRODISPLAY$weight.OTF'));
        }
        await loader.load();
      }
    });

/// Every line of [text] is drawn, none cut short, and the whole of it sits inside [viewport].
void _expectFullyShown(WidgetTester tester, Finder text, Rect viewport, String what) {
  expect(text, findsOneWidget, reason: '$what is missing');
  final paragraph = tester.renderObject<RenderParagraph>(text);
  expect(paragraph.didExceedMaxLines, isFalse, reason: '$what is cut off');
  expect(paragraph.size.height, greaterThanOrEqualTo(paragraph.getMaxIntrinsicHeight(paragraph.size.width) - 0.5),
      reason: '$what is squeezed');
  final rect = tester.getRect(text);
  expect(viewport.top <= rect.top && rect.bottom <= viewport.bottom, isTrue,
      reason: '$what is drawn at $rect, outside the visible sheet $viewport');
}

/// The button is tappable and its whole label is drawn: no ellipsis, no clipping by the button or
/// the screen.
void _expectFullLabel(WidgetTester tester, Key key, String label) {
  final button = find.byKey(key);
  _expectReachable(button);
  final text = find.descendant(of: button, matching: find.text(label));
  expect(text, findsOneWidget);
  final paragraph = tester.renderObject<RenderParagraph>(text);
  expect(paragraph.didExceedMaxLines, isFalse, reason: '"$label" is cut off');
  expect(paragraph.size.height, greaterThanOrEqualTo(paragraph.getMaxIntrinsicHeight(paragraph.size.width) - 0.5),
      reason: '"$label" is squeezed');
  final textRect = tester.getRect(text);
  final buttonRect = tester.getRect(button);
  final screen = Offset.zero & tester.view.physicalSize / tester.view.devicePixelRatio;
  expect(buttonRect.top <= textRect.top && textRect.bottom <= buttonRect.bottom, isTrue,
      reason: '"$label" spills out of its button');
  expect(screen.top <= textRect.top && textRect.bottom <= screen.bottom - tester.view.padding.bottom, isTrue,
      reason: '"$label" is off screen');
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  for (final scale in _textScales) {
    testWidgets('cancel flow keeps Continue, Skip and Cancel Subscription on screen at text scale $scale',
        (tester) async {
      final usage = _proPayer();
      final home = await _pumpHost(tester, scale, usage);
      bool? result;
      Navigator.of(home)
          .push<bool>(
              MaterialPageRoute(builder: (_) => CancelSubscriptionFlow(loadOffer: () async => _retentionOffer())))
          .then((value) => result = value);
      await tester.pumpAndSettle();
      final l10n = AppLocalizations.of(tester.element(find.byType(CancelSubscriptionFlow)));

      // Step 1: the reasons scroll with the title; Continue stays put.
      final reason = find.text(l10n.cancelReasonOther);
      await tester.ensureVisible(reason);
      await tester.pumpAndSettle();
      await tester.tap(reason);
      await tester.pumpAndSettle();
      _expectReachable(_button(l10n.continueButton));
      await tester.tap(_button(l10n.continueButton));
      await tester.pumpAndSettle();

      // Step 2: feedback.
      expect(find.text(l10n.tellUsMore), findsOneWidget);
      _expectReachable(_button(l10n.continueButton));
      _expectReachable(_button(l10n.skipForNow));
      await tester.tap(_button(l10n.skipForNow));
      await tester.pumpAndSettle();

      // Step 3: the retention offer never pushes Cancel off screen.
      expect(find.text(l10n.justAMoment), findsOneWidget);
      _expectReachable(_button(l10n.retentionOfferAccept(50)));
      _expectReachable(_button(l10n.cancelSubscription));
      await tester.tap(_button(l10n.cancelSubscription));
      await tester.pump();
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();

      expect(usage.cancelReasons, ['other']);
      expect(result, isTrue);
      expect(tester.takeException(), isNull);
    });

    testWidgets('cancel flow without an offer keeps Keep and Cancel on screen at text scale $scale', (tester) async {
      final home = await _pumpHost(tester, scale, _proPayer());
      bool? result;
      Navigator.of(home)
          .push<bool>(MaterialPageRoute(builder: (_) => CancelSubscriptionFlow(loadOffer: () async => null)))
          .then((value) => result = value);
      await tester.pumpAndSettle();
      final l10n = AppLocalizations.of(tester.element(find.byType(CancelSubscriptionFlow)));

      final reason = find.text(l10n.cancelReasonTooExpensive);
      await tester.ensureVisible(reason);
      await tester.pumpAndSettle();
      await tester.tap(reason);
      await tester.pumpAndSettle();
      await tester.tap(_button(l10n.continueButton));
      await tester.pumpAndSettle();
      await tester.tap(_button(l10n.continueButton));
      await tester.pumpAndSettle();

      _expectReachable(_button(l10n.keepSubscription));
      _expectReachable(_button(l10n.cancelSubscription));
      await tester.tap(_button(l10n.keepSubscription));
      await tester.pumpAndSettle();
      expect(result, isFalse);
      expect(tester.takeException(), isNull);
    });

    testWidgets('30-day offer sheet reaches Claim and No Thanks at text scale $scale', (tester) async {
      final home = await _pumpHost(tester, scale, _Usage());
      PaywallPrice? checkoutPrice;
      bool? result;
      showOmiSheet<bool>(
        context: home,
        showCloseButton: false,
        builder: (_) => TrialUpsellContent(
          offer: _offer,
          price: _offer.yearly!,
          source: 'test',
          checkout: (_, price, __) async {
            checkoutPrice = price;
            return PaywallCheckoutOutcome.cancelled;
          },
        ),
      ).then((value) => result = value);
      await tester.pumpAndSettle();

      final sheetScroll = find.descendant(of: find.byType(TrialUpsellContent), matching: find.byType(Scrollable));
      final position = tester.state<ScrollableState>(sheetScroll).position;
      if (scale == 1.0) {
        // Default text fits as before: nothing to scroll.
        expect(position.maxScrollExtent, 0);
      } else {
        expect(position.maxScrollExtent, greaterThan(0));
        await tester.drag(sheetScroll, const Offset(0, -3000));
        await tester.pumpAndSettle();
      }

      // At the end of the sheet the price terms sit on screen with the button that commits, and both
      // labels show in full (the old fixed 56 pt pill cut Claim to "Claim my").
      final l10n = AppLocalizations.of(tester.element(find.byType(TrialUpsellContent)));
      _expectReachable(find.byKey(const Key('trial_upsell_price_terms')));
      _expectFullLabel(tester, const Key('trial_upsell_claim'), l10n.trialUpsellClaim(TrialUpsellSheet.trialDays));
      _expectFullLabel(tester, const Key('trial_upsell_decline'), l10n.noThanks);
      expect(
        tester.getRect(find.byKey(const Key('trial_upsell_price_terms'))).bottom,
        lessThanOrEqualTo(tester.getRect(find.byKey(const Key('trial_upsell_claim'))).top),
      );
      await tester.tap(find.byKey(const Key('trial_upsell_claim')));
      await tester.pumpAndSettle();
      expect(checkoutPrice, _offer.yearly);

      await tester.tap(find.byKey(const Key('trial_upsell_decline')));
      await tester.pumpAndSettle();
      expect(result, isFalse);
      expect(tester.takeException(), isNull);
    });
  }

  // A 375 x 667 phone (iPhone SE) at the largest text, in a right-to-left and a long left-to-right
  // locale: the whole renewal price and interval stay on screen with the whole Claim label.
  for (final locale in const [Locale('ar'), Locale('ro')]) {
    testWidgets('30-day offer shows the full price beside the full Claim label on a small phone in $locale',
        (tester) async {
      await _loadSfPro(tester);
      final home = await _pumpHost(tester, _textScales.last, _Usage(), size: _iphoneSE, locale: locale);
      var claims = 0;
      showOmiSheet<bool>(
        context: home,
        showCloseButton: false,
        builder: (_) => TrialUpsellContent(
          offer: _offer,
          price: _offer.yearly!,
          source: 'test',
          checkout: (_, __, ___) async {
            claims++;
            return PaywallCheckoutOutcome.cancelled;
          },
        ),
      );
      await tester.pumpAndSettle();
      final sheet = tester.element(find.byType(TrialUpsellContent));
      final l10n = AppLocalizations.of(sheet);
      expect(Directionality.of(sheet), locale.languageCode == 'ar' ? TextDirection.rtl : TextDirection.ltr);

      final sheetScroll = find.descendant(of: find.byType(TrialUpsellContent), matching: find.byType(Scrollable));
      await tester.drag(sheetScroll, const Offset(0, -3000));
      await tester.pumpAndSettle();
      final viewport = tester.getRect(sheetScroll);

      final priceLine = _offer.yearly!.trialLabel(sheet, TrialUpsellSheet.trialDays);
      expect(priceLine, contains(_offer.yearly!.formatted));
      final priceTerms = find.byKey(const Key('trial_upsell_price_terms'));
      expect(tester.widget<Text>(priceTerms).data, priceLine);
      _expectFullyShown(tester, priceTerms, viewport, 'the price line "$priceLine"');
      final claimLabel = l10n.trialUpsellClaim(TrialUpsellSheet.trialDays);
      _expectFullyShown(
          tester,
          find.descendant(of: find.byKey(const Key('trial_upsell_claim')), matching: find.text(claimLabel)),
          viewport,
          'the Claim label "$claimLabel"');
      _expectFullLabel(tester, const Key('trial_upsell_claim'), claimLabel);
      _expectFullLabel(tester, const Key('trial_upsell_decline'), l10n.noThanks);

      await tester.tap(find.byKey(const Key('trial_upsell_claim')));
      await tester.pumpAndSettle();
      expect(claims, 1);
      expect(tester.takeException(), isNull);
    });
  }
}
