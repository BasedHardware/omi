import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/speech_profile_widget.dart';
import 'package:omi/pages/onboarding/guided_voice_controller.dart';
import '../providers/guided_voice_controller_test.dart' show FakeVoiceIO;

Future<void> pump(WidgetTester tester, GuidedVoiceController flow,
    {double scale = 1, Size size = const Size(390, 844), VoidCallback? skip, VoidCallback? next}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(MaterialApp(
    theme: ThemeData.dark(),
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    builder: (context, child) =>
        MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)), child: child!),
    home: Scaffold(body: SpeechProfileWidget(controller: flow, goNext: next ?? () {}, onSkip: skip ?? () {})),
  ));
}

void main() {
  testWidgets('explicit start, meaningful prompt, alternative and skip without recording', (tester) async {
    final io = FakeVoiceIO();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    var skipped = false;
    await pump(tester, flow, skip: () => skipped = true);
    expect(find.text('Let Omi get to know you'), findsOneWidget);
    expect(io.audio, isNull);
    expect(find.textContaining('My name is'), findsOneWidget);
    await tester.tap(find.byKey(const Key('introduction_another')));
    await tester.pump();
    expect(find.textContaining('My favorite food'), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('speech_profile_skip_intro')));
    await tester.tap(find.byKey(const Key('speech_profile_skip_intro')));
    await tester.pump();
    expect(skipped, isTrue);
  });

  testWidgets('recording has separate audio feedback and prompt progress, then editable review', (tester) async {
    final io = FakeVoiceIO();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await pump(tester, flow);
    await tester.tap(find.byKey(const Key('speech_profile_start')));
    await tester.pump();
    io.speak();
    await tester.pump();
    expect(find.byKey(const Key('introduction_audio_level')), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('introduction_next')));
    await tester.tap(find.byKey(const Key('introduction_next')));
    await tester.pumpAndSettle();
    expect(flow.promptIndex, 1);
    expect(flow.active, isTrue);
    expect(find.byKey(const Key('speech_profile_start')), findsNothing);
    await flow.skipPrompt();
    await flow.skipPrompt();
    await flow.skipPrompt();
    await tester.pumpAndSettle();
    expect(find.text('Here is what I heard'), findsOneWidget);
    expect(find.byType(TextFormField), findsOneWidget);
    expect(find.text('Voice profile saved'), findsNothing);
    expect(io.remembered, isEmpty);
  });

  testWidgets('short phone and large text can scroll to actions without overflow', (tester) async {
    final flow = GuidedVoiceController(FakeVoiceIO());
    addTearDown(flow.dispose);
    await pump(tester, flow, scale: 2, size: const Size(320, 568));
    await tester.ensureVisible(find.byKey(const Key('speech_profile_start')));
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('goal is labeled separately and only saved after review', (tester) async {
    final io = FakeVoiceIO();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    for (var i = 0; i < 3; i++) {
      await flow.skipPrompt();
    }
    await pump(tester, flow);
    expect(find.textContaining('Right now my number one goal'), findsOneWidget);
    await flow.start();
    io.text = 'Launch my project';
    io.speak();
    await flow.next();
    await tester.pumpAndSettle();
    expect(find.text('My goal'), findsOneWidget);
    expect(io.goals, isEmpty);
    await tester.tap(find.byKey(const Key('introduction_save_all')));
    await tester.pumpAndSettle();
    expect(io.goals, ['Launch my project']);
    expect(io.remembered, isEmpty);
    expect(find.text('Your goal is saved'), findsOneWidget);
  });

  testWidgets('one save action saves voice and goal and exits without Continue', (tester) async {
    final io = FakeVoiceIO();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    for (var i = 0; i < 3; i++) {
      await flow.skipPrompt();
    }
    await flow.start();
    io.text = 'Right now my number one goal is to ship Omi.';
    io.speak();
    await flow.next();
    var exits = 0;
    await pump(tester, flow, next: () => exits++);
    expect(find.text('Ship Omi'), findsOneWidget);
    expect(find.text('Save and finish'), findsOneWidget);
    await tester.tap(find.byKey(const Key('introduction_save_all')));
    await tester.pumpAndSettle();
    expect(io.uploads, hasLength(1));
    expect(io.goals, ['Ship Omi']);
    expect(exits, 1);
  });

  testWidgets('original goal wording can be restored before saving', (tester) async {
    final io = FakeVoiceIO();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    for (var i = 0; i < 3; i++) {
      await flow.skipPrompt();
    }
    await flow.start();
    io.text = 'My goal is to ship Omi.';
    io.speak();
    await flow.next();
    await pump(tester, flow);
    await tester.ensureVisible(find.text('Use original wording'));
    await tester.tap(find.text('Use original wording'));
    await tester.pumpAndSettle();
    expect(find.text('My goal is to ship Omi.'), findsOneWidget);
    expect(flow.answers.single.text, io.text);
  });

  testWidgets('review stays usable on a small phone with large text and keyboard', (tester) async {
    final io = FakeVoiceIO();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    for (var i = 0; i < 3; i++) {
      await flow.skipPrompt();
    }
    await flow.start();
    io.speak();
    await flow.next();
    await pump(tester, flow, size: const Size(320, 568), scale: 2);
    tester.view.viewInsets = const FakeViewPadding(bottom: 240);
    addTearDown(tester.view.resetViewInsets);
    await tester.pump();
    await tester.ensureVisible(find.byType(TextFormField));
    await tester.tap(find.byType(TextFormField));
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('introduction_save_all')).hitTestable(), findsOneWidget);
  });

  testWidgets('failed upload remains actionable and never shows success', (tester) async {
    final io = FakeVoiceIO()..uploadSuccess = false;
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await flow.start();
    io.speak();
    await flow.next();
    await flow.skipPrompt();
    await flow.skipPrompt();
    await flow.skipPrompt();
    await flow.saveVoice();
    await pump(tester, flow);
    expect(find.text('Voice profile saved'), findsNothing);
    expect(find.byKey(const Key('introduction_save_all')), findsOneWidget);
    expect(find.byKey(const Key('introduction_leave_review')), findsOneWidget);
  });

  testWidgets('both save receipts render together, and do not collide', (tester) async {
    // saveAll() enrolls the voice before uploading the answers, so this pairing is
    // the normal path for every successful save, not a race. Rendered flush, the
    // spinner and the check sat on one leading edge and read as a broken glyph.
    final io = FakeVoiceIO()..pendingMemory = Completer<void>();
    final flow = GuidedVoiceController(io);
    addTearDown(flow.dispose);
    await flow.start();
    io.speak();
    await flow.next();
    await flow.skipPrompt();
    await flow.skipPrompt();
    await flow.skipPrompt();
    await pump(tester, flow);

    unawaited(flow.saveAll());
    await tester.pump();
    await tester.pump();

    final saving = find.text('Saving your answers…');
    final saved = find.text('Voice profile saved');
    expect(saving, findsOneWidget);
    expect(saved, findsOneWidget, reason: 'the voice is enrolled first, so its receipt is already up');

    final savingRect = tester.getRect(saving);
    final savedRect = tester.getRect(saved);
    expect(
      savedRect.top - savingRect.bottom,
      greaterThanOrEqualTo(12.0),
      reason: 'the two receipts must be separated like the done view, not stacked flush',
    );

    io.pendingMemory!.complete();
    await tester.pumpAndSettle();
  });
}
