import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/people_wire.g.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/speaker_tag_prompt_card.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';

Person _person(String id, String name, {bool pinned = false, String confidence = 'likely'}) => Person(
      id: id,
      name: name,
      createdAt: DateTime.utc(2026, 9, 1),
      updatedAt: DateTime.utc(2026, 9, 1),
      pinned: pinned,
      confidence: confidence,
      confidenceReasons: const [GeneratedPersonConfidenceReason(code: 'card_picks', count: 2)],
    );

GeneratedSpeakerTagPrompt _prompt(
  String id,
  String kind, {
  List<GeneratedSpeakerTagCandidate>? candidates,
  List<String>? suggestedPersonIds,
}) =>
    GeneratedSpeakerTagPrompt(
      id: id,
      kind: kind,
      origin: kind == 'confirm_person' ? 'auto_person' : 'unnamed',
      conversationId: 'c1',
      conversationTitle: 'Coffee chat',
      conversationStartedAt: DateTime.now().subtract(const Duration(hours: 3)),
      speakerId: 1,
      segmentIds: const ['s1'],
      clipStart: 0,
      clipEnd: 8,
      excerpt: 'We should ship it on Friday',
      suggestedPersonId: kind == 'confirm_person' ? 'p1' : null,
      suggestedPersonName: kind == 'confirm_person' ? 'Sam' : null,
      suggestedPersonIds: suggestedPersonIds,
      candidates: candidates,
    );

class _Harness {
  _Harness(this.provider, this.people, this.answers, this.saves);

  final SpeakerTagPromptsProvider provider;
  final PeopleProvider people;
  final List<GeneratedSpeakerTagPromptAnswerRequest> answers;
  final List<bool?> saves;
}

Future<_Harness> _pumpCard(
  WidgetTester tester, {
  required List<GeneratedSpeakerTagPrompt> prompts,
  bool firstTime = false,
  List<Person> people = const [],
  bool loadPeople = true,
  double textScale = 1,
  bool reduceMotion = false,
}) async {
  final answers = <GeneratedSpeakerTagPromptAnswerRequest>[];
  final saves = <bool?>[];
  final provider = SpeakerTagPromptsProvider(
    fetchPrompts: () async => ApiSuccess(GeneratedSpeakerTagPromptsResponse(prompts: prompts, firstTime: firstTime)),
    markShown: (_) async => ApiSuccess(firstTime),
    dismiss: () async => const ApiSuccess<void>(null),
    submitAnswer: (request) async {
      answers.add(request);
      return ApiSuccess(GeneratedSpeakerTagPromptAnswerResponse(
        qualityOutcome: 'skipped',
        personId: request.personId ?? (request.answer == 'new_person' ? 'p-new' : null),
      ));
    },
    updateSettings: ({bool? speakerTagPromptsEnabled, bool? saveOtherVoiceProfiles, required String source}) async {
      saves.add(saveOtherVoiceProfiles);
      return ApiSuccess(GeneratedVoiceProfileSettings(saveOtherVoiceProfiles: saveOtherVoiceProfiles ?? true));
    },
    emit: (_) {},
    answeredHold: Duration.zero,
  );
  final peopleProvider = PeopleProvider(loadPeople: () async => people);
  if (loadPeople) await peopleProvider.setPeople();
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<PeopleProvider>.value(value: peopleProvider),
        ChangeNotifierProvider.value(value: provider),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: TextScaler.linear(textScale), disableAnimations: reduceMotion),
          child: child!,
        ),
        home: const Scaffold(body: SingleChildScrollView(child: SpeakerTagPromptCard())),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return _Harness(provider, peopleProvider, answers, saves);
}

/// Lets the 5 s Undo window close so the staged answer commits.
Future<void> _waitOutUndo(WidgetTester tester) async {
  // The toast's 5 s timer starts once its entrance animation has finished.
  await tester.pump();
  await tester.pump(const Duration(seconds: 1));
  await tester.pump(const Duration(seconds: 6));
  await tester.pumpAndSettle();
}

Future<void> _tapKey(WidgetTester tester, String key) async {
  final finder = find.byKey(Key(key));
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
  });

  testWidgets('voice-card answers and play expose accessibility tap actions', (tester) async {
    final handle = tester.ensureSemantics();
    await _pumpCard(tester, prompts: [_prompt('a', 'owner_check')]);
    for (final key in ['speaker_tag_prompt_answer_me', 'speaker_tag_prompt_play']) {
      final node = tester.getSemantics(find.byKey(Key(key)));
      expect(node.getSemanticsData().hasAction(SemanticsAction.tap), isTrue, reason: key);
    }
    await tester.pumpWidget(const SizedBox.shrink());
    await _pumpCard(tester, prompts: [
      _prompt('b', 'identify', candidates: [
        const GeneratedSpeakerTagCandidate(personId: 'p1', name: 'Maya', matchLevel: 2),
      ])
    ]);
    expect(
        tester
            .getSemantics(find.byKey(const Key('speaker_tag_prompt_candidate_p1')))
            .getSemanticsData()
            .hasAction(SemanticsAction.tap),
        isTrue);
    handle.dispose();
  });

  testWidgets('voice-card controls support 200 percent text and Reduce Motion', (tester) async {
    await _pumpCard(tester, prompts: [_prompt('a', 'owner_check')], textScale: 2, reduceMotion: true);
    expect(tester.takeException(), isNull);
    final chip = find.byKey(const Key('speaker_tag_prompt_answer_not_a_person'));
    expect(tester.getSize(chip).height, greaterThanOrEqualTo(44));
    for (final widget in tester.widgetList<AnimatedOpacity>(find.byType(AnimatedOpacity))) {
      expect(widget.duration, Duration.zero);
    }
  });

  testWidgets('owner then confirm: answers send after their Undo window, then the card thanks the user',
      (tester) async {
    final h = await _pumpCard(
      tester,
      prompts: [_prompt('a', 'owner_check'), _prompt('b', 'confirm_person')],
      people: [_person('p1', 'Sam')],
    );
    expect(find.text('Is this you?'), findsOneWidget);
    expect(find.textContaining('We should ship it on Friday'), findsOneWidget);
    expect(find.textContaining('Coffee chat'), findsOneWidget);
    expect(find.byKey(const Key('speaker_tag_prompt_save_voices_switch')), findsNothing);

    await _tapKey(tester, 'speaker_tag_prompt_answer_me');
    await tester.pump();
    // Staged: the answered state and an Undo toast show, nothing is sent yet.
    expect(find.byKey(const Key('speaker_tag_prompt_answered')), findsOneWidget);
    expect(find.text('Undo'), findsOneWidget);
    expect(h.answers, isEmpty);
    await _waitOutUndo(tester);
    expect(h.answers.map((a) => a.answer), ['me']);

    expect(find.text('Is this Sam?'), findsOneWidget);
    expect(find.text('Yes raises Sam\'s confidence.'), findsOneWidget);
    await _tapKey(tester, 'speaker_tag_prompt_answer_yes');
    await tester.pump();
    expect(find.text('Saved as Sam'), findsOneWidget);
    await _waitOutUndo(tester);
    expect(h.answers.map((a) => a.answer), ['me', 'person']);
    expect(h.answers.last.personId, 'p1');
    expect(find.byKey(const Key('speaker_tag_prompt_done')), findsOneWidget);

    await tester.tap(find.byKey(const Key('speaker_tag_prompt_done')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('speaker_tag_prompt_card')), findsNothing);
  });

  testWidgets('Undo drops a staged answer and puts the question back', (tester) async {
    final h = await _pumpCard(tester, prompts: [_prompt('a', 'identify')]);
    await _tapKey(tester, 'speaker_tag_prompt_answer_not_a_person');
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Marked as not a person'), findsOneWidget);
    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(h.answers, isEmpty);
    expect(h.provider.pending, isNull);
    expect(find.text('Who is this?'), findsOneWidget);
  });

  testWidgets('Not a Person commits the not_a_person answer', (tester) async {
    final h = await _pumpCard(tester, prompts: [_prompt('a', 'confirm_person')], people: [_person('p1', 'Sam')]);
    await _tapKey(tester, 'speaker_tag_prompt_answer_not_a_person');
    await _waitOutUndo(tester);
    expect(h.answers.single.answer, 'not_a_person');
  });

  testWidgets('Not Sure skips at once, without Undo', (tester) async {
    final h = await _pumpCard(tester, prompts: [_prompt('a', 'identify'), _prompt('b', 'owner_check')]);
    await _tapKey(tester, 'speaker_tag_prompt_answer_skip');
    await tester.pumpAndSettle();
    expect(h.answers.single.answer, 'skip');
    expect(find.text('Is this you?'), findsOneWidget);
  });

  testWidgets('identify ranks server candidates by voice match, pinned first, and a pick sends that person',
      (tester) async {
    final h = await _pumpCard(
      tester,
      prompts: [
        _prompt('a', 'identify', candidates: const [
          GeneratedSpeakerTagCandidate(personId: 'p2', name: 'Jordan', matchLevel: 2, pinned: true),
          GeneratedSpeakerTagCandidate(personId: 'p3', name: 'Alex', matchLevel: 1),
        ]),
      ],
      people: [_person('p2', 'Jordan', pinned: true), _person('p3', 'Alex')],
    );
    expect(find.text('Closest voices'), findsOneWidget);
    final jordan = tester.getTopLeft(find.byKey(const Key('speaker_tag_prompt_candidate_p2')));
    final alex = tester.getTopLeft(find.byKey(const Key('speaker_tag_prompt_candidate_p3')));
    expect(jordan.dx < alex.dx || jordan.dy < alex.dy, isTrue);
    expect(find.bySemanticsLabel(RegExp(r'Jordan, Pinned, Voice match: Possible match')), findsOneWidget);

    await _tapKey(tester, 'speaker_tag_prompt_candidate_p3');
    await _waitOutUndo(tester);
    expect(h.answers.single.answer, 'person');
    expect(h.answers.single.personId, 'p3');
  });

  testWidgets('legacy suggested people appear once the people list loads after the card', (tester) async {
    final h = await _pumpCard(
      tester,
      prompts: [
        _prompt('a', 'identify', suggestedPersonIds: ['p2'])
      ],
      people: [_person('p2', 'Ana')],
      loadPeople: false,
    );
    expect(find.byKey(const Key('speaker_tag_prompt_candidate_p2')), findsNothing);
    await h.people.setPeople();
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('speaker_tag_prompt_candidate_p2')), findsOneWidget);
    expect(find.text('People you talked to recently'), findsOneWidget);
  });

  testWidgets('Someone Else… names who it is: the picker leaves out the person just ruled out', (tester) async {
    final h = await _pumpCard(
      tester,
      prompts: [_prompt('a', 'confirm_person'), _prompt('b', 'confirm_person')],
      people: [_person('p1', 'Sam'), _person('p4', 'Priya')],
    );
    await _tapKey(tester, 'speaker_tag_prompt_answer_someone_else');
    await tester.pumpAndSettle();
    expect(find.text('Who Is It?'), findsOneWidget);
    expect(find.byKey(const Key('speaker_picker_person_p1')), findsNothing);
    await tester.tap(find.byKey(const Key('speaker_picker_person_p4')));
    await _waitOutUndo(tester);
    expect(h.answers.single.answer, 'person');
    expect(h.answers.single.personId, 'p4');

    // A typed name that matches no one becomes a new person.
    await _tapKey(tester, 'speaker_tag_prompt_answer_someone_else');
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Dana');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Add “Dana”'));
    await _waitOutUndo(tester);
    expect(h.answers.last.answer, 'new_person');
    expect(h.answers.last.name, 'Dana');
  });

  testWidgets("Someone Else… can say it is someone the user doesn't know", (tester) async {
    final h = await _pumpCard(tester, prompts: [_prompt('a', 'confirm_person')], people: [_person('p1', 'Sam')]);
    await _tapKey(tester, 'speaker_tag_prompt_answer_someone_else');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('speaker_picker_unknown')));
    await _waitOutUndo(tester);
    expect(h.answers.single.answer, 'someone_else');
    expect(h.answers.single.personId, isNull);
  });

  testWidgets('first set shows the save-voices switch and a new person can be named in the iOS dialog', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    try {
      final h = await _pumpCard(tester, prompts: [_prompt('a', 'identify')], firstTime: true);
      final toggle = find.byKey(const Key('speaker_tag_prompt_save_voices_switch'));
      await tester.ensureVisible(toggle);
      await tester.pumpAndSettle();
      await tester.tap(toggle);
      await tester.pumpAndSettle();
      expect(h.saves, [false]);

      await _tapKey(tester, 'speaker_tag_prompt_answer_someone_else');
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('speaker_picker_new_person')));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.enterText(find.byKey(const Key('speaker_tag_prompt_name_field')), 'Ana');
      await tester.pump();
      await tester.tap(find.byKey(const Key('speaker_tag_prompt_name_save')));
      await _waitOutUndo(tester);
      expect(h.answers.single.answer, 'new_person');
      expect(h.answers.single.name, 'Ana');
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  });

  testWidgets('clip 404 advances to the next prompt without a dead card', (tester) async {
    final provider = SpeakerTagPromptsProvider(
      fetchPrompts: () async => ApiSuccess(
        GeneratedSpeakerTagPromptsResponse(prompts: [_prompt('a', 'owner_check'), _prompt('b', 'confirm_person')]),
      ),
      markShown: (_) async => const ApiSuccess(false),
      loadClip: (item) async => item.id == 'a'
          ? const ApiFailure(ApiProblem(ApiProblemKind.notFound, statusCode: 404))
          : ApiSuccess(Uint8List.fromList([1])),
      playClip: (_, __) async => true,
      emit: (_) {},
    );
    addTearDown(provider.dispose);
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => PeopleProvider(loadPeople: () async => [])),
          ChangeNotifierProvider.value(value: provider),
        ],
        child: const MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: SingleChildScrollView(child: SpeakerTagPromptCard())),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Is this you?'), findsOneWidget);
    await tester.tap(find.byKey(const Key('speaker_tag_prompt_play')));
    await tester.pumpAndSettle();
    expect(find.text('Is this Sam?'), findsOneWidget);
    expect(provider.current?.id, 'b');
    expect(provider.answeredCount, 0);
  });

  test('waveform levels come from the clip samples, scaled to the loudest bar', () {
    final samples = ByteData(44 + 8 * 2);
    for (var i = 0; i < 8; i++) {
      samples.setInt16(44 + i * 2, i < 4 ? 1000 : 4000, Endian.little);
    }
    final levels = waveformLevels(samples.buffer.asUint8List(), bars: 2);
    expect(levels, hasLength(2));
    expect(levels[1], 1.0);
    expect(levels[0], closeTo(0.25, 0.001));
    expect(waveformLevels(Uint8List(10)), isEmpty);
  });
}
