import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_intro_screen.dart';

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
  // Regression: the forced first-run tour soft-locked users when a step hung
  // (e.g. the mic-test "processing your question"). The intro must always
  // offer a skip, and the back arrow must always be present.
  testWidgets('intro screen shows Skip for now below Get Started and fires onSkip', (tester) async {
    var started = false;
    var skipped = false;
    await tester.pumpWidget(_app(OnboardingIntroScreen(onStart: () => started = true, onSkip: () => skipped = true)));
    await tester.pump();

    final skipFinder = find.byKey(const Key('device_onboarding_skip_button'));
    expect(skipFinder, findsOneWidget);

    // Back arrow is always visible (no allowExit gating anymore).
    expect(find.byIcon(Icons.arrow_back_ios_new), findsOneWidget);

    await tester.tap(skipFinder);
    expect(skipped, isTrue);
    expect(started, isFalse);
  });

  testWidgets('back arrow fires onSkip', (tester) async {
    var skipped = false;
    await tester.pumpWidget(_app(OnboardingIntroScreen(onStart: () {}, onSkip: () => skipped = true)));
    await tester.pump();

    await tester.tap(find.byIcon(Icons.arrow_back_ios_new));
    expect(skipped, isTrue);
  });
}
