import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/speech_profile_provider.dart';
import 'package:omi/widgets/onboarding_progress_bar.dart';

class _RecordingAuthProvider extends AuthenticationProvider {
  _RecordingAuthProvider() : super(initializeListeners: false);

  int localEmulatorSignInCalls = 0;
  bool _signedIn = false;

  @override
  bool isSignedIn() => _signedIn;

  @override
  Future<void> onLocalEmulatorSignIn(Function() onSignIn) async {
    localEmulatorSignInCalls++;
    _signedIn = true;
    onSignIn();
  }

  @override
  Future<void> onGoogleSignIn(Function() onSignIn) async {}
}

Future<void> _debugSkip(WidgetTester tester) async {
  await tester.longPress(find.byType(OnboardingProgressBar));
  await tester.pump(const Duration(milliseconds: 450));
}

// SpeechProfileWidget reads SpeechProfileProvider from an ancestor (the
// app-root instance in main.dart) instead of owning one itself, so tests
// that pump OnboardingWrapper directly need to provide one too.
Widget _wrapOnboarding(
  AuthenticationProvider authProvider,
  SpeechProfileProvider speechProfileProvider, {
  bool forceStartAtSplash = false,
}) {
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<AuthenticationProvider>.value(value: authProvider),
      ChangeNotifierProvider<SpeechProfileProvider>.value(value: speechProfileProvider),
    ],
    child: MaterialApp(
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: OnboardingWrapper(forceStartAtSplash: forceStartAtSplash),
    ),
  );
}

void main() {
  // Regression: the debug-only long-press skip (kDebugMode, so it never
  // ships) is the only way to get past onboarding steps whose Continue
  // button is gated on a real backend call in local dev builds — it must
  // actually advance the TabController, not just fire the gesture.
  testWidgets('debug long-press advances to the next onboarding step', (tester) async {
    final authProvider = _RecordingAuthProvider();
    addTearDown(authProvider.dispose);
    final speechProfileProvider = SpeechProfileProvider();
    addTearDown(speechProfileProvider.dispose);

    await tester.pumpWidget(_wrapOnboarding(authProvider, speechProfileProvider));
    await tester.pump();

    // Splash -> sign-in. OnboardingWrapper's spinner backdrop repeats
    // forever from the moment it mounts, so every settle below is a bounded
    // pump instead of pumpAndSettle.
    await tester.tap(find.text('Get Started'));
    await tester.pump(const Duration(milliseconds: 450));
    expect(find.text('Speak. Transcribe. Summarize.'), findsOneWidget);

    await _debugSkip(tester);
    expect(find.text('Data & Privacy'), findsOneWidget);
  });

  // Holding Apple/Google used to hit OnboardingWrapper's 500ms debug skip
  // and advance past auth with no token, so speech-profile Get Started
  // showed a connection error. The skip is only on the progress bar now.
  testWidgets('holding Google does not debug-skip the auth page', (tester) async {
    final authProvider = _RecordingAuthProvider();
    addTearDown(authProvider.dispose);
    final speechProfileProvider = SpeechProfileProvider();
    addTearDown(speechProfileProvider.dispose);

    await tester.pumpWidget(_wrapOnboarding(authProvider, speechProfileProvider));
    await tester.pump();
    await tester.tap(find.text('Get Started'));
    await tester.pump(const Duration(milliseconds: 450));

    final gesture = await tester.startGesture(tester.getCenter(find.byKey(const Key('googleSignIn'))));
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.text('Speak. Transcribe. Summarize.'), findsOneWidget);
    expect(find.text('Data & Privacy'), findsNothing);
    expect(authProvider.localEmulatorSignInCalls, 0);

    await gesture.up();
    await tester.pump();
  });

  // Regression: onboarding used to have a "What's your primary language?"
  // step between Name and Found Omi, letting the user pick their language.
  // It's now set to English automatically and the step is gone — advancing
  // past Name must land straight on Found Omi.
  testWidgets('onboarding has no primary-language step between name and found-omi', (tester) async {
    final authProvider = _RecordingAuthProvider();
    addTearDown(authProvider.dispose);
    final speechProfileProvider = SpeechProfileProvider();
    addTearDown(speechProfileProvider.dispose);

    await tester.pumpWidget(_wrapOnboarding(authProvider, speechProfileProvider));
    await tester.pump();

    // Splash -> sign-in -> data & privacy -> name, via the debug skip.
    // OnboardingWrapper's spinner backdrop repeats forever from the moment
    // it mounts, so every settle below is a bounded pump instead of
    // pumpAndSettle.
    await tester.tap(find.text('Get Started'));
    await tester.pump(const Duration(milliseconds: 450));
    await _debugSkip(tester);
    await _debugSkip(tester);
    expect(find.text("What's your name?"), findsOneWidget);

    // Name -> the next step must be Found Omi, not a language picker.
    await _debugSkip(tester);
    expect(find.text('How did you find us?'), findsOneWidget);
    expect(find.text("What's your primary language?"), findsNothing);
  });

  // Regression: a fully-onboarded returning user's "Agree & Continue" on
  // data & privacy jumps straight to home (deliberately, so they don't
  // re-run onboarding). Debug restart (forceStartAtSplash) exists so a dev
  // can walk the whole flow regardless of persisted state — it must bypass
  // this shortcut too, or the flow still gets cut short right after consent.
  testWidgets('forced debug restart walks past data & privacy instead of jumping to home', (tester) async {
    SharedPreferences.setMockInitialValues({'onboardingCompleted': true});
    final authProvider = _RecordingAuthProvider();
    addTearDown(authProvider.dispose);
    final speechProfileProvider = SpeechProfileProvider();
    addTearDown(speechProfileProvider.dispose);

    await tester.pumpWidget(
      _wrapOnboarding(authProvider, speechProfileProvider, forceStartAtSplash: true),
    );
    await tester.pump();

    await tester.tap(find.text('Get Started'));
    await tester.pump(const Duration(milliseconds: 450));
    await _debugSkip(tester);
    expect(find.text('Data & Privacy'), findsOneWidget);

    // Real tap on the actual consent button, not the debug skip — this is
    // what runs AiConsentWidget's onAgree and its onboardingCompleted check.
    await tester.tap(find.text('Agree & Continue'));
    await tester.pump(const Duration(milliseconds: 450));
    expect(find.text("What's your name?"), findsOneWidget);
  });
}
