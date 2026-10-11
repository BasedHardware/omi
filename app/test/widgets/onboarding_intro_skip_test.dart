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
  // offer a skip, and a way out must always be present. The tour floats over the app, so the way
  // out is a trailing close X (docs/ux-contract.md §1), not a back chevron that means "quit".
  testWidgets('intro screen shows Skip below Get Started and fires onSkip', (tester) async {
    var started = false;
    var skipped = false;
    await tester.pumpWidget(_app(OnboardingIntroScreen(
      onStart: () => started = true,
      onSkip: () => skipped = true,
    )));
    await tester.pump();

    final skipFinder = find.byKey(const Key('device_onboarding_skip_button'));
    expect(skipFinder, findsOneWidget);

    // The close X is always visible (no allowExit gating anymore), and no back chevron is drawn.
    expect(find.byKey(const Key('device_onboarding_close_button')), findsOneWidget);
    expect(find.byIcon(Icons.arrow_back_ios_new), findsNothing);
    expect(find.text('Skip'), findsOneWidget);

    await tester.tap(skipFinder);
    expect(skipped, isTrue);
    expect(started, isFalse);
  });

  testWidgets('close X fires onSkip and is labelled', (tester) async {
    var skipped = false;
    await tester.pumpWidget(_app(OnboardingIntroScreen(
      onStart: () {},
      onSkip: () => skipped = true,
    )));
    await tester.pump();

    expect(find.bySemanticsLabel('Close'), findsOneWidget);
    await tester.tap(find.byKey(const Key('device_onboarding_close_button')));
    expect(skipped, isTrue);
  });
}
