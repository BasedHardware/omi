import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/providers/auth_provider.dart';

class _FakeAuthProvider extends AuthenticationProvider {
  _FakeAuthProvider() : super(initializeListeners: false);

  @override
  bool isSignedIn() => false;
}

void main() {
  // Regression: the debug-only long-press skip (kDebugMode, so it never
  // ships) is the only way to get past onboarding steps whose Continue
  // button is gated on a real backend call in local dev builds — it must
  // actually advance the TabController, not just fire the gesture.
  testWidgets('debug long-press advances to the next onboarding step', (tester) async {
    final authProvider = _FakeAuthProvider();
    addTearDown(authProvider.dispose);

    await tester.pumpWidget(
      ChangeNotifierProvider<AuthenticationProvider>.value(
        value: authProvider,
        child: const MaterialApp(
          localizationsDelegates: [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: OnboardingWrapper(),
        ),
      ),
    );
    await tester.pump();

    // Splash -> sign-in. OnboardingWrapper's spinner backdrop repeats
    // forever from the moment it mounts, so every settle below is a bounded
    // pump instead of pumpAndSettle.
    await tester.tap(find.text('Get Started'));
    await tester.pump(const Duration(milliseconds: 700));
    expect(find.text('Speak. Transcribe. Summarize.'), findsOneWidget);

    // Long-press should skip straight to data & privacy, bypassing auth.
    await tester.longPress(find.text('Speak. Transcribe. Summarize.'));
    await tester.pump(const Duration(milliseconds: 700));
    expect(find.text('Data & Privacy'), findsOneWidget);
  });

  // Regression: onboarding used to have a "What's your primary language?"
  // step between Name and Found Omi, letting the user pick their language.
  // It's now set to English automatically and the step is gone — advancing
  // past Name must land straight on Found Omi.
  testWidgets('onboarding has no primary-language step between name and found-omi', (tester) async {
    final authProvider = _FakeAuthProvider();
    addTearDown(authProvider.dispose);

    await tester.pumpWidget(
      ChangeNotifierProvider<AuthenticationProvider>.value(
        value: authProvider,
        child: const MaterialApp(
          localizationsDelegates: [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: OnboardingWrapper(),
        ),
      ),
    );
    await tester.pump();

    // Splash -> sign-in -> data & privacy -> name, via the debug skip.
    // OnboardingWrapper's spinner backdrop repeats forever from the moment
    // it mounts, so every settle below is a bounded pump instead of
    // pumpAndSettle.
    await tester.tap(find.text('Get Started'));
    await tester.pump(const Duration(milliseconds: 700));
    await tester.longPress(find.text('Speak. Transcribe. Summarize.'));
    await tester.pump(const Duration(milliseconds: 700));
    await tester.longPress(find.text('Data & Privacy'));
    await tester.pump(const Duration(milliseconds: 700));
    expect(find.text("What's your name?"), findsOneWidget);

    // Name -> the next step must be Found Omi, not a language picker.
    await tester.longPress(find.text("What's your name?"));
    await tester.pump(const Duration(milliseconds: 700));
    expect(find.text('How did you find us?'), findsOneWidget);
    expect(find.text("What's your primary language?"), findsNothing);
  });
}
