import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/activation/activation_capture.dart';
import 'package:omi/pages/onboarding/activation/activation_flow.dart';

class _FakeCapture implements ActivationCapture {
  _FakeCapture(this.result);

  final ActivationResult result;
  final ValueNotifier<String> live = ValueNotifier('');
  bool cancelled = false;

  @override
  bool get usesDevice => false;

  @override
  ValueListenable<String> get liveText => live;

  @override
  Future<bool> start() async => true;

  @override
  Future<ActivationResult> finish({Duration timeout = const Duration(seconds: 30)}) async => result;

  @override
  Future<void> cancel() async => cancelled = true;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  const notes = ActivationResult(
    transcript: 'Remind me to send the deck',
    emoji: '🥗',
    title: 'Lunch with Sam',
    overview: 'Sam is moving to Lisbon in June.',
    tasks: ['Send the deck to the team by Friday', 'Grab milk on the way home'],
  );

  Future<({_FakeCapture capture, List<String> events})> pump(
    WidgetTester tester, {
    bool hasDevice = false,
    ActivationResult result = notes,
    Completer<void>? paywall,
  }) async {
    final capture = _FakeCapture(result);
    final events = <String>[];
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
          body: ActivationFlow(
            hasDevice: hasDevice,
            capture: (_) => capture,
            microphoneGranted: () async => true,
            requestReview: () async => events.add('review'),
            showPaywall: () {
              events.add('paywall');
              return paywall?.future ?? Future.value();
            },
            onFinished: () => events.add('finished'),
          ),
        ),
      ),
    );
    return (capture: capture, events: events);
  }

  Future<void> tapKey(WidgetTester tester, String key) async {
    await tester.tap(find.byKey(Key(key)));
    await tester.pump(const Duration(seconds: 5));
  }

  testWidgets('the full path: intro, dictation, notes, tasks, hooray, rating, paywall, Home', (tester) async {
    final paywall = Completer<void>();
    final run = await pump(tester, paywall: paywall);

    expect(find.text("Let's see Omi at work."), findsNothing, reason: 'words appear one by one');
    await tester.pump(const Duration(seconds: 4)); // Moves on by itself, straight to the dictation.

    // Dictation: the check stays off until Omi has heard something.
    expect(find.text('Tell Omi about your day'), findsOneWidget);
    await tester.tap(find.byKey(const Key('activation_dictation_done')));
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Tell Omi about your day'), findsOneWidget, reason: 'nothing heard yet');
    run.capture.live.value = 'Remind me to send the deck';
    await tester.pump();
    await tapKey(tester, 'activation_dictation_done');

    expect(find.text('Your notes'), findsOneWidget);
    expect(find.text('🥗  Lunch with Sam'), findsOneWidget);
    await tapKey(tester, 'activation_continue_summary');

    expect(find.text('Your tasks'), findsOneWidget);
    expect(find.text('Grab milk on the way home'), findsOneWidget);
    await tapKey(tester, 'activation_continue_tasks');

    // Hooray, then the rating ask, then the paywall.
    expect(find.byKey(const Key('activation_continue_congrats')), findsOneWidget);
    expect(run.events, isEmpty);
    await tapKey(tester, 'activation_continue_congrats');
    await tester.pump(const Duration(seconds: 2)); // The pop-up waits for the stars.
    expect(find.text('Enjoying Omi so far?'), findsOneWidget);
    expect(run.events, ['review'], reason: 'the App Store pop-up opens by itself');

    // The pop-up makes the app inactive; its closing opens the paywall, and closing that goes Home.
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    expect(run.events, ['review', 'paywall']);
    paywall.complete();
    await tester.pump();
    expect(run.events, ['review', 'paywall', 'finished']);
  });

  testWidgets('device owners see the wear step first', (tester) async {
    await pump(tester, hasDevice: true);
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Wear your Omi'), findsOneWidget);
  });

  testWidgets('skipping the dictation leaves a welcome card for Home and goes to the hooray', (tester) async {
    final run = await pump(tester);
    await tester.pump(const Duration(seconds: 4));
    await tapKey(tester, 'activation_dictation_skip');

    expect(run.capture.cancelled, isTrue);
    expect(SharedPreferencesUtil().getBool(ActivationFlow.welcomeCardKey), isTrue);
    expect(find.byKey(const Key('activation_continue_congrats')), findsOneWidget);
    await tester.pump(const Duration(seconds: 3)); // Lets the celebration finish.
  });

  testWidgets('when Omi could not make notes, the reader still sees their own words', (tester) async {
    final run = await pump(tester, result: const ActivationResult(transcript: 'Just testing this out'));
    await tester.pump(const Duration(seconds: 4));
    run.capture.live.value = 'Just testing this out';
    await tester.pump();
    await tapKey(tester, 'activation_dictation_done');

    expect(find.text("Here's what you said"), findsOneWidget);
    await tapKey(tester, 'activation_continue_summary');
    expect(find.byKey(const Key('activation_continue_congrats')), findsOneWidget, reason: 'no tasks step');
    await tester.pump(const Duration(seconds: 3)); // Lets the celebration finish.
  });
}
