import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/pages/paywall/trial_paywall_page.dart';
import 'package:omi/providers/usage_provider.dart';

import '../helpers/sfpro_font_fixtures.dart';
import 'guided_voice_render_test.dart' show loadFonts;

// The trial paywall laid out with the real SF Pro metrics an iPhone uses, not the square test glyphs:
// long Restore labels keep their full size at the default text size, and a small phone at the first
// accessibility size still shows the price line and the button.

const _offer = PaywallOffer(
  tierId: 'unlimited',
  monthly: PaywallPrice(priceId: 'm', interval: 'month', amountMinor: 2999, currency: 'usd'),
  yearly: PaywallPrice(priceId: 'y', interval: 'year', amountMinor: 26991, currency: 'usd'),
);

Future<void> _pump(WidgetTester tester, {required Size size, Locale? locale, double textScale = 1}) async {
  debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
  tester.view.physicalSize = size * 3;
  tester.view.devicePixelRatio = 3;
  tester.view.padding = const FakeViewPadding(top: 47 * 3, bottom: 34 * 3);
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    ChangeNotifierProvider<UsageProvider>(
      create: (_) => UsageProvider(),
      child: MaterialApp(
        locale: locale,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) =>
            MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)), child: child!),
        home: TrialPaywallPage(source: 'onboarding', offer: _offer, now: DateTime(2026, 11, 22)),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

/// How much the Restore label is scaled down by its slot: 1.0 means its full size.
double _restoreScale(WidgetTester tester, String label) {
  final text = find.descendant(of: find.byKey(const Key('trial_paywall_restore')), matching: find.text(label));
  final natural = tester.renderObject<RenderBox>(text).size.width;
  return tester.getRect(text).width / natural;
}

void main() {
  setUpAll(() async {
    await loadFonts();
    for (final family in ['CupertinoSystemText', 'CupertinoSystemDisplay']) {
      final loader = FontLoader(family);
      for (final weight in ['REGULAR', 'MEDIUM', 'BOLD']) {
        loader.addFont(sfProFont('SFPRODISPLAY$weight.OTF'));
      }
      await loader.load();
    }
  });

  for (final (locale, label) in const [(Locale('de'), 'Wiederherstellen'), (Locale('ru'), 'Восстановить')]) {
    testWidgets('${locale.languageCode} Restore keeps its full size at 375pt and the default text size',
        (tester) async {
      await _pump(tester, size: const Size(375, 667), locale: locale);
      expect(tester.takeException(), isNull);
      expect(_restoreScale(tester, label), closeTo(1, 0.001));
      final restore = tester.getRect(find.byKey(const Key('trial_paywall_restore')));
      final brand = tester.getRect(find.byKey(const Key('trial_paywall_brand')));
      expect(restore.right, lessThanOrEqualTo(brand.left), reason: 'Restore $restore vs brand $brand');
      debugDefaultTargetPlatformOverride = null;
    });
  }

  testWidgets('320x568 at 1.6x lays out without overflow, price line and button on screen', (tester) async {
    await _pump(tester, size: const Size(320, 568), textScale: 1.6);
    expect(tester.takeException(), isNull);
    for (final key in const ['trial_paywall_price_terms', 'trial_paywall_cta']) {
      final rect = tester.getRect(find.byKey(Key(key)));
      expect(rect.top, greaterThanOrEqualTo(0), reason: key);
      expect(rect.bottom, lessThanOrEqualTo(568 - 34), reason: key);
    }
    debugDefaultTargetPlatformOverride = null;
  });
}
