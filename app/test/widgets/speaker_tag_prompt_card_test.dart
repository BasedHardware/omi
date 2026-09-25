import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/speaker_tag_prompt_card.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
  });

  Future<(List<GeneratedSpeakerTagPromptAnswerRequest>, List<bool?>)> pumpCard(
    WidgetTester tester, {
    required List<GeneratedSpeakerTagPrompt> prompts,
    bool firstTime = false,
  }) async {
    final answers = <GeneratedSpeakerTagPromptAnswerRequest>[];
    final saves = <bool?>[];
    final provider = SpeakerTagPromptsProvider(
      fetchPrompts: () async => ApiSuccess(GeneratedSpeakerTagPromptsResponse(prompts: prompts, firstTime: firstTime)),
      markShown: (_) async => ApiSuccess(firstTime),
      dismiss: () async => const ApiSuccess<void>(null),
      submitAnswer: (request) async {
        answers.add(request);
        return const ApiSuccess(GeneratedSpeakerTagPromptAnswerResponse(qualityOutcome: 'skipped'));
      },
      updateSettings: ({bool? speakerTagPromptsEnabled, bool? saveOtherVoiceProfiles, required String source}) async {
        saves.add(saveOtherVoiceProfiles);
        return ApiSuccess(GeneratedVoiceProfileSettings(saveOtherVoiceProfiles: saveOtherVoiceProfiles ?? true));
      },
      emit: (_) {},
    );
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => PeopleProvider(loadPeople: () async => [])),
        ChangeNotifierProvider.value(value: provider),
      ],
      child: const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: SingleChildScrollView(child: SpeakerTagPromptCard())),
      ),
    ));
    await tester.pumpAndSettle();
    return (answers, saves);
  }

  GeneratedSpeakerTagPrompt prompt(String id, String kind) => GeneratedSpeakerTagPrompt(
        id: id,
        kind: kind,
        origin: kind == 'confirm_person' ? 'auto_person' : 'unnamed',
        conversationId: 'c1',
        conversationTitle: 'Coffee chat',
        speakerId: 1,
        segmentIds: const ['s1'],
        clipStart: 0,
        clipEnd: 8,
        excerpt: 'We should ship it on Friday',
        suggestedPersonId: kind == 'confirm_person' ? 'p1' : null,
        suggestedPersonName: kind == 'confirm_person' ? 'Sam' : null,
      );

  testWidgets('walks through owner and confirm questions, then thanks the user', (tester) async {
    final (answers, _) = await pumpCard(tester, prompts: [prompt('a', 'owner_check'), prompt('b', 'confirm_person')]);
    expect(find.text('Is this you?'), findsOneWidget);
    expect(find.textContaining('We should ship it on Friday'), findsOneWidget);
    expect(find.byKey(const Key('speaker_tag_prompt_save_voices_switch')), findsNothing);

    await tester.tap(find.byKey(const Key('speaker_tag_prompt_answer_me')));
    await tester.pumpAndSettle();
    expect(find.text('Is this Sam?'), findsOneWidget);

    await tester.tap(find.byKey(const Key('speaker_tag_prompt_answer_yes')));
    await tester.pumpAndSettle();
    expect(answers.map((a) => a.answer), ['me', 'person']);
    expect(answers.last.personId, 'p1');
    expect(find.byKey(const Key('speaker_tag_prompt_done')), findsOneWidget);

    await tester.tap(find.byKey(const Key('speaker_tag_prompt_done')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('speaker_tag_prompt_card')), findsNothing);
  });

  testWidgets('first set shows the save-voices switch and a new name can be typed', (tester) async {
    final (answers, saves) = await pumpCard(tester, prompts: [prompt('a', 'identify')], firstTime: true);
    final toggle = find.byKey(const Key('speaker_tag_prompt_save_voices_switch'));
    expect(toggle, findsOneWidget);
    await tester.tap(toggle);
    await tester.pumpAndSettle();
    expect(saves, [false]);

    final someoneNew = find.byKey(const Key('speaker_tag_prompt_answer_someone_new'));
    await tester.ensureVisible(someoneNew);
    await tester.pumpAndSettle();
    await tester.tap(someoneNew);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('speaker_tag_prompt_name_field')), findsOneWidget);
    await tester.enterText(find.byKey(const Key('speaker_tag_prompt_name_field')), 'Ana');
    await tester.pump();
    final save = tester.widget<TextButton>(find.byKey(const Key('speaker_tag_prompt_name_save')));
    expect(save.onPressed, isNotNull);
    await tester.tap(find.byKey(const Key('speaker_tag_prompt_name_save')));
    await tester.pumpAndSettle();
    expect(answers.single.answer, 'new_person');
    expect(answers.single.name, 'Ana');
  });

  testWidgets('someone new opens a working name field in the iOS dialog', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    try {
      final (answers, _) = await pumpCard(tester, prompts: [prompt('a', 'identify')]);
      await tester.tap(find.byKey(const Key('speaker_tag_prompt_answer_someone_new')));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.enterText(find.byKey(const Key('speaker_tag_prompt_name_field')), 'Ana');
      await tester.pump();
      await tester.tap(find.byKey(const Key('speaker_tag_prompt_name_save')));
      await tester.pumpAndSettle();
      expect(answers.single.name, 'Ana');
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  });

  testWidgets('suggested people appear once the people list loads after the card', (tester) async {
    final people = PeopleProvider(
      loadPeople: () async => [
        Person(id: 'p2', name: 'Ana', createdAt: DateTime.utc(2026, 9, 1), updatedAt: DateTime.utc(2026, 9, 1)),
      ],
    );
    addTearDown(people.dispose);
    final provider = SpeakerTagPromptsProvider(
      fetchPrompts: () async => const ApiSuccess(GeneratedSpeakerTagPromptsResponse(
        prompts: [
          GeneratedSpeakerTagPrompt(
            id: 'a',
            kind: 'identify',
            origin: 'unnamed',
            conversationId: 'c1',
            conversationTitle: 'Coffee chat',
            speakerId: 1,
            segmentIds: ['s1'],
            clipStart: 0,
            clipEnd: 8,
            excerpt: '',
            suggestedPersonIds: ['p2'],
          ),
        ],
        firstTime: false,
      )),
      markShown: (_) async => const ApiSuccess(false),
      emit: (_) {},
    );
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<PeopleProvider>.value(value: people),
        ChangeNotifierProvider.value(value: provider),
      ],
      child: const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: SingleChildScrollView(child: SpeakerTagPromptCard())),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('speaker_tag_prompt_answer_person_p2')), findsNothing);

    await people.setPeople();
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('speaker_tag_prompt_answer_person_p2')), findsOneWidget);
  });
}
