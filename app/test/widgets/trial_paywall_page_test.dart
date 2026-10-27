import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/paywall/paywall_checkout.dart';
import 'package:omi/pages/paywall/trial_paywall_page.dart';
import 'package:omi/providers/usage_provider.dart';

// The trial paywall must lay out without overflow on the narrowest phones Omi supports, on every
// carousel slide, with a long yearly price. Fixed pixel widths in the slide art were the regression.

const _offer = PaywallOffer(
  tierId: 'unlimited',
  monthly: PaywallPrice(priceId: 'm', interval: 'month', amountMinor: 2999, currency: 'usd'),
  yearly: PaywallPrice(priceId: 'y', interval: 'year', amountMinor: 26991, currency: 'usd'),
);

Future<void> _pump(WidgetTester tester, Size size,
    {Brightness brightness = Brightness.light, bool safeArea = false}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    ChangeNotifierProvider(
      create: (_) => UsageProvider(),
      child: MaterialApp(
        theme: ThemeData(brightness: brightness),
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(
            padding: safeArea ? const EdgeInsets.only(top: 59, bottom: 34) : EdgeInsets.zero,
            viewPadding: safeArea ? const EdgeInsets.only(top: 59, bottom: 34) : EdgeInsets.zero,
          ),
          child: child!,
        ),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: TrialPaywallPage(source: 'onboarding', offer: _offer, now: DateTime(2026, 10, 18)),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  for (final brightness in Brightness.values) {
    testWidgets('light paywall keeps readable status chrome and an unclipped 44pt close in $brightness',
        (tester) async {
      await _pump(tester, const Size(393, 852), brightness: brightness, safeArea: true);
      final overlay = tester.widget<AnnotatedRegion<SystemUiOverlayStyle>>(
        find.byType(AnnotatedRegion<SystemUiOverlayStyle>).first,
      );
      expect(overlay.value.statusBarBrightness, Brightness.light);
      expect(overlay.value.statusBarIconBrightness, Brightness.dark);
      final close = find.byKey(const Key('trial_paywall_close'));
      final bounds = tester.getRect(close);
      final header = tester.getRect(find.ancestor(of: close, matching: find.byType(Stack)).first);
      expect(bounds.width, greaterThanOrEqualTo(44));
      expect(bounds.height, greaterThanOrEqualTo(44));
      expect(bounds.top, greaterThanOrEqualTo(59));
      expect(bounds.bottom, lessThanOrEqualTo(header.bottom));
      expect(bounds.top, greaterThanOrEqualTo(header.top));
      expect(close.hitTestable(), findsOneWidget);
      expect(find.byTooltip('Close'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }

  for (final size in const [Size(320, 568), Size(360, 640), Size(430, 932)]) {
    testWidgets('every carousel slide fits at ${size.width.toInt()}pt', (tester) async {
      await _pump(tester, size);
      expect(tester.takeException(), isNull);
      final pageView = find.byType(PageView);
      for (var i = 0; i < 4; i++) {
        await tester.drag(pageView, const Offset(-400, 0));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull, reason: 'slide ${i + 2} overflowed at ${size.width}');
      }
      expect(find.text('Try for US\$0.00'), findsOneWidget);
    });
  }

  testWidgets('scrolling to the plans shows both prices and the yearly saving', (tester) async {
    await _pump(tester, const Size(320, 568));
    final vertical = find.byWidgetPredicate((w) => w is Scrollable && w.axisDirection == AxisDirection.down);
    await tester.scrollUntilVisible(find.text('US\$29.99'), 200, scrollable: vertical.first);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('US\$29.99'), findsOneWidget);
    expect(find.text('US\$269.91'), findsOneWidget);
    expect(find.textContaining('Save US\$89.97'), findsOneWidget);
  });
}
