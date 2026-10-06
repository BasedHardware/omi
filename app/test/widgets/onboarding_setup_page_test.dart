import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/setup_page.dart';

// The "Setting up your Omi" page: the checklist ticks on a timer, the rating pre-prompt appears
// over it, both answers close it (only "Yes" asks the store for a review), and the page advances
// itself once the ticks are done, the pending setup settled and the prompt answered.
//
// Timers drive the page, so the tests pump explicit durations: pumpAndSettle would run every tick
// at once and never settle on the active step's spinner.

const _interval = Duration(milliseconds: 750);
const _promptDelay = Duration(milliseconds: 1200);
const _transition = Duration(milliseconds: 400);

Widget _host(Widget child, {TargetPlatform platform = TargetPlatform.iOS}) {
  return MaterialApp(
    theme: ThemeData(platform: platform),
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

int _doneCount() => find.byKey(const ValueKey('done')).evaluate().length;

void main() {
  testWidgets('steps tick one by one and the page advances once after the last tick', (tester) async {
    var finished = 0;
    await tester.pumpWidget(_host(OnboardingSetupPage(
      onFinished: () => finished++,
      stepInterval: _interval,
      // Keep the prompt out of this test's way.
      ratingPromptDelay: const Duration(hours: 1),
    )));
    await tester.pump();
    expect(find.byKey(const Key('onboarding_setup_page')), findsOneWidget);
    expect(find.text('Setting up your Omi'), findsOneWidget);
    expect(find.text('Give Omi a moment to personalize'), findsOneWidget);
    for (var i = 0; i < OnboardingSetupPage.stepCount; i++) {
      expect(find.byKey(Key('onboarding_setup_step_$i')), findsOneWidget);
    }
    expect(_doneCount(), 0);

    await tester.pump(_interval); // t = 750: first tick
    await tester.pump(_transition);
    expect(_doneCount(), 1);
    await tester.pump(_interval - _transition); // t = 1500: second tick
    await tester.pump(_transition);
    expect(_doneCount(), 2);

    await tester.pump(_interval * 3 - _transition); // t = 3750: last tick
    await tester.pump(_transition);
    expect(_doneCount(), OnboardingSetupPage.stepCount);
    expect(finished, 0, reason: 'the last tick is given a beat before leaving');

    await tester.pump(const Duration(seconds: 1));
    expect(finished, 1);
    await tester.pump(const Duration(seconds: 5));
    expect(finished, 1, reason: 'advances exactly once');
  });

  testWidgets('waits for pending setup, but never longer than the cap', (tester) async {
    var finished = 0;
    final pending = Completer<void>();
    await tester.pumpWidget(_host(OnboardingSetupPage(
      onFinished: () => finished++,
      pendingWork: pending.future,
      stepInterval: _interval,
      maxPendingWait: const Duration(seconds: 3),
      ratingPromptDelay: const Duration(hours: 1),
    )));
    await tester.pump(_interval * OnboardingSetupPage.stepCount); // t = 3750: ticks done
    await tester.pump(const Duration(seconds: 2));
    expect(finished, 0, reason: 'still waiting on real setup');
    await tester.pump(const Duration(seconds: 2)); // cap (3 s) + beat passed
    expect(finished, 1, reason: 'the cap ran out; never block on setup for longer');
  });

  testWidgets('pending setup finishing early releases the page right after the last tick', (tester) async {
    var finished = 0;
    await tester.pumpWidget(_host(OnboardingSetupPage(
      onFinished: () => finished++,
      pendingWork: Future<void>.value(),
      stepInterval: _interval,
      ratingPromptDelay: const Duration(hours: 1),
    )));
    await tester.pump(_interval * OnboardingSetupPage.stepCount);
    await tester.pump(const Duration(seconds: 1));
    expect(finished, 1);
  });

  testWidgets('rating prompt: Yes requests the store review and the page then advances', (tester) async {
    var finished = 0;
    var reviews = 0;
    await tester.pumpWidget(_host(OnboardingSetupPage(
      onFinished: () => finished++,
      stepInterval: _interval,
      ratingPromptDelay: _promptDelay,
      requestReview: () async => reviews++,
    )));
    await tester.pump(_promptDelay - const Duration(milliseconds: 100));
    await tester.pump();
    expect(find.byType(CupertinoAlertDialog), findsNothing);

    await tester.pump(const Duration(milliseconds: 100)); // t = 1200: prompt
    await tester.pump(_transition);
    expect(find.byType(CupertinoAlertDialog), findsOneWidget, reason: 'native-style alert on iOS');
    expect(find.text('While you wait, has Omi been nice to use?'), findsOneWidget);
    expect(find.text('Rating us 5 stars really helps us out ❤️'), findsOneWidget);
    expect(find.byKey(const Key('onboarding_rating_yes')), findsOneWidget);
    expect(find.byKey(const Key('onboarding_rating_no')), findsOneWidget);

    // Ticks keep going behind the alert, but the page holds until it is answered.
    await tester.pump(_interval * OnboardingSetupPage.stepCount + const Duration(seconds: 2));
    expect(_doneCount(), OnboardingSetupPage.stepCount);
    expect(finished, 0);

    await tester.tap(find.byKey(const Key('onboarding_rating_yes')));
    await tester.pump();
    await tester.pump(_transition);
    expect(find.byType(CupertinoAlertDialog), findsNothing);
    expect(reviews, 1);
    expect(finished, 1);
  });

  testWidgets('rating prompt: Not really just closes the alert', (tester) async {
    var reviews = 0;
    var finished = 0;
    await tester.pumpWidget(_host(OnboardingSetupPage(
      onFinished: () => finished++,
      stepInterval: const Duration(hours: 1),
      ratingPromptDelay: _promptDelay,
      requestReview: () async => reviews++,
    )));
    await tester.pump(_promptDelay);
    await tester.pump(_transition);
    expect(find.byType(CupertinoAlertDialog), findsOneWidget);
    await tester.tap(find.byKey(const Key('onboarding_rating_no')));
    await tester.pump();
    await tester.pump(_transition);
    expect(find.byType(CupertinoAlertDialog), findsNothing);
    expect(reviews, 0);
    expect(finished, 0, reason: 'declining never skips the setup');
  });

  testWidgets('uses a Material alert on Android', (tester) async {
    await tester.pumpWidget(_host(
      OnboardingSetupPage(
        onFinished: () {},
        stepInterval: const Duration(hours: 1),
        ratingPromptDelay: _promptDelay,
        requestReview: () async {},
      ),
      platform: TargetPlatform.android,
    ));
    await tester.pump(_promptDelay);
    await tester.pump(_transition);
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(find.byType(CupertinoAlertDialog), findsNothing);
    await tester.tap(find.byKey(const Key('onboarding_rating_no')));
    await tester.pump();
    await tester.pump(_transition);
    expect(find.byType(AlertDialog), findsNothing);
  });
}
