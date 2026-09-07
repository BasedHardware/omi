import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/splash/splash_page.dart';

Widget _app(Widget child) {
  return MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(body: child),
  );
}

void main() {
  testWidgets('splash page shows the Omi wordmark, tagline, and fires goNext on Get Started', (tester) async {
    var startedOnboarding = false;
    await tester.pumpWidget(_app(OnboardingSplashPage(goNext: () => startedOnboarding = true)));
    await tester.pump();

    expect(find.text('Omi'), findsOneWidget);
    expect(find.text('your second brain.'), findsOneWidget);
    expect(find.widgetWithText(ElevatedButton, 'Get Started'), findsOneWidget);
    expect(find.byIcon(Icons.arrow_forward), findsNothing);

    await tester.tap(find.widgetWithText(ElevatedButton, 'Get Started'));
    // Get Started plays a shrink-and-glow exit animation on the device
    // before advancing — settle it before asserting.
    await tester.pumpAndSettle();
    expect(startedOnboarding, isTrue);
  });
}
