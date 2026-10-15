import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/variants/yinka/activation/activation_capture.dart';
import 'package:omi/pages/onboarding/variants/yinka/activation/activation_flow.dart';

class _FakeCapture implements ActivationCapture {
  _FakeCapture(this.result, {this.startsAs = ActivationStart.listening, this.device = false});

  final ActivationResult result;
  final ActivationStart startsAs;
  final bool device;
  final ValueNotifier<String> live = ValueNotifier('');
  bool cancelled = false;

  @override
  bool get usesDevice => device;

  @override
  ValueListenable<String> get liveText => live;

  final ValueNotifier<double> levelNotifier = ValueNotifier(0);

  @override
  ValueListenable<double> get level => levelNotifier;

  @override
  Future<ActivationStart> start() async => startsAs;

  @override
  Future<ActivationResult> finish({Duration timeout = const Duration(seconds: 30)}) async => result;

  @override
  Future<void> cancel() async => cancelled = true;
}

/// Omi never finishes its notes (a slow network or a slow server).
class _SlowCapture extends _FakeCapture {
  _SlowCapture() : super(const ActivationResult(transcript: ''));

  @override
  Future<ActivationResult> finish({Duration timeout = const Duration(seconds: 30)}) =>
      Completer<ActivationResult>().future;
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
    _FakeCapture Function()? capture,
    Future<bool> Function()? requestMicrophone,
    Future<bool> Function()? finish,
  }) async {
    final captures = <_FakeCapture>[];
    _FakeCapture next() {
      final made = (captures.isEmpty ? capture?.call() : null) ?? _FakeCapture(result);
      captures.add(made);
      return made;
    }

    final first = next();
    var used = false;
    final events = <String>[];
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
          body: ActivationFlow(
            hasDevice: hasDevice,
            capture: (_) {
              if (!used) {
                used = true;
                return first;
              }
              return next();
            },
            microphoneGranted: () async => true,
            requestMicrophone: requestMicrophone,
            requestReview: () async => events.add('review'),
            showPaywall: () {
              events.add('paywall');
              return paywall?.future ?? Future.value();
            },
            onFinished: () async {
              events.add('finished');
              return finish == null ? true : await finish();
            },
          ),
        ),
      ),
    );
    return (capture: first, events: events);
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

    expect(find.text('Your day, summarized'), findsOneWidget);
    expect(find.text('Lunch with Sam'), findsOneWidget);
    expect(find.text('Just now'), findsOneWidget);
    await tapKey(tester, 'activation_continue_summary');

    expect(find.text('Omi caught your to-dos'), findsOneWidget);
    expect(find.text('Grab milk on the way home'), findsOneWidget);
    expect(find.text('Saved to your tasks'), findsOneWidget);
    await tapKey(tester, 'activation_continue_tasks');

    // Hooray, then the rating ask, then the paywall.
    expect(find.byKey(const Key('activation_continue_congrats')), findsOneWidget);
    expect(run.events, isEmpty);
    await tapKey(tester, 'activation_continue_congrats');
    await tester.pump(const Duration(seconds: 2)); // The pop-up waits for the stars.
    expect(find.text('Enjoying Omi so far?'), findsOneWidget);
    expect(run.events, ['review'], reason: 'the App Store pop-up opens by itself');
    // The stars sit right under the title, above where the pop-up opens.
    final titleBottom = tester.getBottomLeft(find.text('Enjoying Omi so far?')).dy;
    final starsTop = tester.getTopLeft(find.byIcon(Icons.star_rounded).first).dy;
    expect(starsTop - titleBottom, lessThan(40));

    // The pop-up makes the app inactive; its closing opens the paywall, and closing that goes Home.
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    expect(run.events, ['review', 'paywall']);
    paywall.complete();
    await tester.pump();
    expect(run.events, ['review', 'paywall', 'finished']);
  });

  testWidgets('rating: once the App Store pop-up is up, it moves on to the paywall by itself', (tester) async {
    final run = await pump(tester);
    await tester.pump(const Duration(seconds: 4));
    run.capture.live.value = 'Remind me to send the deck';
    await tester.pump();
    await tapKey(tester, 'activation_dictation_done');
    await tapKey(tester, 'activation_continue_summary');
    await tapKey(tester, 'activation_continue_tasks');
    await tapKey(tester, 'activation_continue_congrats');

    // A tap before the pop-up has been asked for stays on the rating screen.
    await tester.tapAt(tester.getCenter(find.text('Enjoying Omi so far?')));
    await tester.pump();
    expect(run.events, isEmpty);

    await tester.pump(const Duration(seconds: 2));
    expect(run.events, ['review'], reason: 'the pop-up is asked for, not yet on screen');

    // iOS gives no cue when its pop-up closes: the paywall opens underneath it instead.
    await tester.pump(const Duration(seconds: 1));
    expect(run.events, ['review', 'paywall', 'finished']);
  });

  testWidgets('Omi owners go straight to the intro (how to wear it is the button tutorial before it)', (tester) async {
    await pump(tester, hasDevice: true);
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Wear your Omi'), findsNothing);
    await tester.pump(const Duration(seconds: 5));
  });

  testWidgets('when the Omi is not streaming, the microphone is asked for before the dictation', (tester) async {
    var asked = false;
    await pump(
      tester,
      hasDevice: true,
      capture: () => _FakeCapture(notes, startsAs: ActivationStart.needsMicrophone),
      requestMicrophone: () async => asked = true,
    );
    await tester.pump(const Duration(seconds: 4));
    await tester.pump(const Duration(seconds: 1));
    expect(find.text("Your Omi isn't sending audio yet. Use your phone for now."), findsOneWidget);
    await tapKey(tester, 'activation_continue_microphone');
    expect(asked, isTrue);
    expect(find.text('Tell Omi about your day'), findsOneWidget, reason: 'listening again, through the phone');
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 13));
  });

  testWidgets('after a quiet stretch the dictation says it cannot hear the Omi', (tester) async {
    await pump(tester, hasDevice: true, capture: () => _FakeCapture(notes, device: true));
    await tester.pump(const Duration(seconds: 4));
    await tester.pump(const Duration(seconds: 13));
    expect(find.text("Can't hear your Omi. Make sure it's on and close by."), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 1));
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

  testWidgets('slow notes: after the deadline the reader moves on with their words, told notes are coming',
      (tester) async {
    final run = await pump(tester, capture: _SlowCapture.new);
    await tester.pump(const Duration(seconds: 4));
    run.capture.live.value = 'Lunch with Sam today';
    await tester.pump();
    await tester.tap(find.byKey(const Key('activation_dictation_done')));
    await tester.pump(const Duration(seconds: 5));
    expect(find.text('Summarizing…'), findsOneWidget, reason: 'still within the deadline');

    await tester.pump(const Duration(seconds: 8)); // Past the 12 s deadline.
    await tester.pump(const Duration(seconds: 5));
    expect(find.text("Here's what you said"), findsOneWidget);
    expect(find.text('Lunch with Sam today'), findsOneWidget);
    expect(find.textContaining('still writing'), findsNothing, reason: 'no apology line; the notes reach Home');
    expect(find.text("Omi remembers so you don't have to"), findsOneWidget);
    await tapKey(tester, 'activation_continue_summary');
    expect(find.byKey(const Key('activation_continue_congrats')), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('when listening cannot start, Continue moves on instead of a dead end', (tester) async {
    await pump(tester, capture: () => _FakeCapture(notes, startsAs: ActivationStart.failed));
    await tester.pump(const Duration(seconds: 4));
    await tester.pump();
    expect(find.byKey(const Key('activation_dictation_status')), findsOneWidget);
    await tapKey(tester, 'activation_continue_dictation');
    expect(find.byKey(const Key('activation_continue_congrats')), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('when nothing is heard for a while, Continue appears; late words bring the check back', (tester) async {
    final run = await pump(tester);
    await tester.pump(const Duration(seconds: 4));
    expect(find.byKey(const Key('activation_continue_dictation')), findsNothing);
    await tester.pump(const Duration(seconds: 26));
    expect(find.byKey(const Key('activation_continue_dictation')), findsOneWidget);

    run.capture.live.value = 'Finally some words';
    await tester.pump();
    expect(find.byKey(const Key('activation_continue_dictation')), findsNothing);
    expect(find.byKey(const Key('activation_dictation_done')), findsOneWidget);
  });

  testWidgets('a failed final save keeps Continue working; the paywall is not shown twice', (tester) async {
    var attempts = 0;
    final run = await pump(tester, finish: () async => ++attempts > 1);
    await tester.pump(const Duration(seconds: 4));
    await tester.tap(find.text('Skip'));
    await tester.pump(const Duration(seconds: 5));
    await tapKey(tester, 'activation_continue_congrats');
    await tester.pump(const Duration(seconds: 2));
    await tester.tap(find.byKey(const Key('activation_continue_rating')), warnIfMissed: false);
    await tester.pump();
    expect(run.events, ['review'], reason: 'Continue waits for the App Store prompt');
    await tester.pump(const Duration(seconds: 2));
    expect(run.events, ['review', 'paywall', 'finished'], reason: 'moves on by itself; the first save fails');

    await tapKey(tester, 'activation_continue_rating');
    expect(run.events, ['review', 'paywall', 'finished', 'finished'], reason: 'retried without a second paywall');
    expect(attempts, 2);
  });

  testWidgets('Omi visibly hears the person: the voice ring and meter follow the level', (tester) async {
    final run = await pump(tester);
    await tester.pump(const Duration(seconds: 4));
    await tester.pump();
    final ring = find.byKey(const Key('activation_voice_ring'));
    expect(ring, findsOneWidget);
    expect(find.byKey(const Key('activation_level_meter')), findsOneWidget);
    final quiet = tester.getSize(ring).width;

    run.capture.levelNotifier.value = 1;
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(tester.getSize(ring).width, greaterThan(quiet + 40));
  });
}
