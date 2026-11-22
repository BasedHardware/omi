import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/pages/paywall/trial_paywall_page.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/usage_provider.dart';

// The trial paywall's trust pass: Terms and Privacy at the button, one dated charge row, a header
// where Restore never runs into the brand, and a price line, button and legal line that stay on
// screen at a large text size. The button still opens the same checkout with the same plan.

const _offer = PaywallOffer(
  tierId: 'unlimited',
  monthly: PaywallPrice(priceId: 'm', interval: 'month', amountMinor: 2999, currency: 'usd'),
  yearly: PaywallPrice(priceId: 'y', interval: 'year', amountMinor: 26991, currency: 'usd'),
);

/// iPhone 17 Pro in points, with its safe areas.
const _phone = Size(402, 874);
// The test font draws every glyph as a full square, about twice as wide as SF Pro, so 2x here lays
// out like the largest accessibility size does on a phone. The simulator shots check the real 3.12x.
const _largeText = 2.0;

class _Usage extends UsageProvider {
  @override
  UserSubscriptionResponse get subscription => UserSubscriptionResponse(
        trialEligible: true,
        subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
        transcriptionSecondsUsed: 0,
        transcriptionSecondsLimit: 18000,
        wordsTranscribedUsed: 0,
        wordsTranscribedLimit: 0,
        insightsGainedUsed: 0,
        insightsGainedLimit: 0,
        showSubscriptionUi: true,
      );
}

class _Auth extends AuthenticationProvider {
  _Auth() : super(initializeListeners: false);

  final opened = <String>[];

  @override
  void openTermsOfService() => opened.add('terms');

  @override
  void openPrivacyPolicy() => opened.add('privacy');
}

typedef _Call = ({String priceId, String interval, int amountMinor, String tierId});

Future<(_Auth, List<_Call>)> _pump(WidgetTester tester, {double textScale = 1}) async {
  tester.view.physicalSize = _phone * 3;
  tester.view.devicePixelRatio = 3;
  tester.view.padding = const FakeViewPadding(top: 62 * 3, bottom: 34 * 3);
  addTearDown(tester.view.reset);
  final auth = _Auth();
  final calls = <_Call>[];
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<UsageProvider>(create: (_) => _Usage()),
        ChangeNotifierProvider<AuthenticationProvider>.value(value: auth),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
          child: child!,
        ),
        home: TrialPaywallPage(
          source: 'onboarding',
          offer: _offer,
          now: DateTime(2026, 11, 22),
          checkout: (_, price, tierId) async {
            calls.add(
                (priceId: price.priceId, interval: price.interval, amountMinor: price.amountMinor, tierId: tierId));
            return PaywallCheckoutOutcome.failed;
          },
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return (auth, calls);
}

/// Fully inside the visible screen, not under the status bar or the home indicator.
void _expectOnScreen(WidgetTester tester, Finder finder, String what) {
  expect(finder, findsOneWidget, reason: what);
  final rect = tester.getRect(finder);
  expect(rect.top, greaterThanOrEqualTo(0), reason: '$what top');
  expect(rect.bottom, lessThanOrEqualTo(_phone.height - 34), reason: '$what bottom');
}

void main() {
  testWidgets('Terms of Use and Privacy Policy sit under the button and open their pages', (tester) async {
    final (auth, _) = await _pump(tester);
    expect(tester.takeException(), isNull);
    final terms = find.byKey(const Key('trial_paywall_terms'));
    final privacy = find.byKey(const Key('trial_paywall_privacy'));
    expect(find.text('Terms of Use'), findsOneWidget);
    expect(find.text('Privacy Policy'), findsOneWidget);
    final cta = tester.getRect(find.byKey(const Key('trial_paywall_cta')));
    for (final link in [terms, privacy]) {
      final rect = tester.getRect(link);
      expect(rect.top, greaterThanOrEqualTo(cta.bottom), reason: 'legal line is under the button');
      expect(rect.height, greaterThanOrEqualTo(44), reason: '44pt target');
      expect(rect.width, greaterThanOrEqualTo(44), reason: '44pt target');
    }
    await tester.tap(terms);
    await tester.tap(privacy);
    expect(auth.opened, ['terms', 'privacy']);
  });

  testWidgets('the timeline carries one dated charge row', (tester) async {
    await _pump(tester);
    expect(find.text('Nov 22, 2026'), findsOneWidget);
    expect(find.text('Nov 29, 2026'), findsOneWidget, reason: 'only the charge row carries the trial end date');
    expect(find.text('Today'), findsOneWidget);
    expect(find.text('In 7 days'), findsOneWidget);
  });

  testWidgets('the carousel says its first title once', (tester) async {
    await _pump(tester);
    final carousel = find.byType(PageView);
    expect(find.descendant(of: carousel, matching: find.text('Unlimited summaries, kept forever')), findsOneWidget);
  });

  testWidgets('at the default text size the header stays 44pt tall', (tester) async {
    await _pump(tester);
    expect(tester.getRect(find.byKey(const Key('trial_paywall_restore'))).height, 44);
    expect(tester.getRect(find.byKey(const Key('trial_paywall_close'))).height, 44);
    expect(tester.getRect(find.text('Omi Pro').first).center.dx, _phone.width / 2);
  });

  testWidgets('at a large text size Restore never overlaps the brand or Close', (tester) async {
    await _pump(tester, textScale: _largeText);
    expect(tester.takeException(), isNull);
    final restore = tester.getRect(find.byKey(const Key('trial_paywall_restore')));
    final brand = tester.getRect(find.text('Omi Pro').first);
    final close = tester.getRect(find.byKey(const Key('trial_paywall_close')));
    expect(restore.right, lessThanOrEqualTo(brand.left), reason: 'Restore $restore vs brand $brand');
    expect(brand.right, lessThanOrEqualTo(close.left), reason: 'brand $brand vs Close $close');
  });

  testWidgets('at a large text size the price, button and legal line show without scrolling', (tester) async {
    await _pump(tester, textScale: _largeText);
    expect(tester.takeException(), isNull);
    _expectOnScreen(tester, find.byKey(const Key('trial_paywall_price_terms')), 'price line');
    _expectOnScreen(tester, find.byKey(const Key('trial_paywall_cta')), 'button');
    _expectOnScreen(tester, find.byKey(const Key('trial_paywall_terms')), 'Terms of Use');
    _expectOnScreen(tester, find.byKey(const Key('trial_paywall_privacy')), 'Privacy Policy');
    final priceTop = tester.getRect(find.byKey(const Key('trial_paywall_price_terms'))).top;
    expect(priceTop, greaterThan(_phone.height * 0.3), reason: 'the pinned footer leaves the page room');
  });

  testWidgets('at the default text size the cancel note and code hint stay pinned under the button', (tester) async {
    await _pump(tester);
    final legal = tester.getRect(find.byKey(const Key('trial_paywall_privacy')));
    final note = tester.getRect(find.text('Cancel anytime. No fees, no penalties.'));
    final hint = tester.getRect(find.byKey(const Key('trial_paywall_code_hint')));
    expect(note.top, greaterThanOrEqualTo(legal.bottom));
    expect(hint.top, greaterThanOrEqualTo(note.bottom));
    expect(hint.bottom, lessThanOrEqualTo(_phone.height - 34));
    final noteStyle = tester.widget<Text>(find.text('Cancel anytime. No fees, no penalties.')).style!;
    expect(noteStyle.color, const Color(0xFF6E6E73), reason: 'secondary grey, not green');
    expect(noteStyle.fontWeight, FontWeight.w400);
  });

  testWidgets('the button still opens the yearly trial checkout for the same plan', (tester) async {
    final (_, calls) = await _pump(tester);
    await tester.tap(find.byKey(const Key('trial_paywall_cta')));
    await tester.pump();
    expect(calls, [(priceId: 'y', interval: 'year', amountMinor: 26991, tierId: 'unlimited')]);
    expect(find.text('Try for US\$0.00'), findsOneWidget);
    expect(find.text('7 days free, then US\$269.91/year'), findsWidgets);
  });
}
