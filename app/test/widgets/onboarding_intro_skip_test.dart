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
  // (e.g. the mic-test "processing your question"). A way out must always be present. The tour
  // floats over the app, so the way out is a trailing close X (docs/ux-contract.md §1), not a back
  // chevron that means "quit" — and not a second Skip under Get Started as well.
  testWidgets('intro screen leaves by the close X only, with no Skip under Get Started', (tester) async {
    var started = false;
    await tester.pumpWidget(_app(OnboardingIntroScreen(onStart: () => started = true, onSkip: () {})));
    await tester.pump();

    expect(find.byKey(const Key('device_onboarding_close_button')), findsOneWidget);
    expect(find.byKey(const Key('device_onboarding_skip_button')), findsNothing);
    expect(find.text('Skip'), findsNothing);
    expect(find.byIcon(Icons.arrow_back_ios_new), findsNothing);

    await tester.tap(find.text('Get Started'));
    expect(started, isTrue);
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
