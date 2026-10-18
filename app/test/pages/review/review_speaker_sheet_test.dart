import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/review/review_item_sheet.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';

Person _person(String id, String name) => Person(
      id: id,
      name: name,
      createdAt: DateTime.utc(2026, 9, 1),
      updatedAt: DateTime.utc(2026, 9, 1),
    );

/// Two voice candidates: Béla is also in the people list, Riley is not (the server can rank
/// someone the cached list has not caught up with).
const _speaker = ReviewItem(
  itemId: 'speaker:p1',
  kind: ReviewItemKind.speaker,
  quote: 'See you Friday.',
  speaker: SpeakerItem(
    promptId: 'p1',
    conversationId: 'c9',
    conversationTitle: 'Sync',
    start: 0,
    end: 5,
    candidates: [PersonRef(personId: 'p-bela', name: 'Béla'), PersonRef(personId: 'p-riley', name: 'Riley')],
  ),
);

Future<ReviewProvider> _review(List<(String, Map<String, dynamic>)> sent) async {
  final provider = ReviewProvider(
    isEligible: () => true,
    reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
    loadItems: () async => const ApiSuccess(ReviewItemsResponse(items: [_speaker], remainingToday: 1)),
    sendAnswer: (item, answer) async {
      sent.add((item.itemId, answer.toJson(item.kind)));
      return const ApiSuccess(0);
    },
  );
  await provider.load();
  return provider;
}

Future<void> _pumpSheet(
  WidgetTester tester, {
  required ReviewProvider review,
  required List<Person> people,
  void Function()? onDone,
}) async {
  final peopleProvider = PeopleProvider(loadPeople: () async => PeopleListResponse(people: people));
  await peopleProvider.setPeople();
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<ReviewProvider>.value(value: review),
        ChangeNotifierProvider<PeopleProvider>.value(value: peopleProvider),
      ],
      child: MaterialApp(
        theme: buildOmiTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: ListView(
            children: [ReviewItemDetail(item: _speaker, onDone: onDone)],
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _openPicker(WidgetTester tester) async {
  await tester.tap(find.byKey(const Key('review_speaker_someone_else')));
  await tester.pumpAndSettle();
}

Map<String, dynamic> _speakerAnswer(List<(String, Map<String, dynamic>)> sent) =>
    sent.single.$2['speaker'] as Map<String, dynamic>;

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('the sheet keeps the candidate chips and Me, and Someone Else… opens a searchable picker',
      (tester) async {
    final sent = <(String, Map<String, dynamic>)>[];
    await _pumpSheet(tester,
        review: await _review(sent), people: [_person('p-dana', 'Dana'), _person('p-alex', 'Alex')]);
    expect(find.text('Béla'), findsOneWidget);
    expect(find.text('Me'), findsOneWidget);

    await _openPicker(tester);
    expect(find.text('Who Is It?'), findsOneWidget);
    expect(find.byType(OmiSearchField), findsOneWidget);
    // No That's Me / Not a Person / "don't know": the sheet answers those itself.
    expect(find.byKey(const Key('speaker_picker_me')), findsNothing);
    expect(find.byKey(const Key('speaker_picker_not_a_person')), findsNothing);
    expect(find.byKey(const Key('speaker_picker_unknown')), findsNothing);
    // The candidates repeat under Closest voices; everyone else is searchable A to Z.
    expect(find.text('Closest voices'), findsOneWidget);
    expect(find.byKey(const Key('speaker_picker_person_p-bela')), findsOneWidget);
    expect(find.text('Everyone'), findsOneWidget);
    expect(find.byKey(const Key('speaker_picker_person_p-dana')), findsOneWidget);
    expect(find.byKey(const Key('speaker_picker_person_p-alex')), findsOneWidget);
  });

  testWidgets('picking an existing person from the picker sends that person', (tester) async {
    final sent = <(String, Map<String, dynamic>)>[];
    var closed = false;
    await _pumpSheet(
      tester,
      review: await _review(sent),
      people: [_person('p-dana', 'Dana')],
      onDone: () => closed = true,
    );
    await _openPicker(tester);
    await tester.tap(find.byKey(const Key('speaker_picker_person_p-dana')));
    await tester.pumpAndSettle();
    expect(find.text('Confirm Dana'), findsOneWidget);

    await tester.tap(find.byKey(const Key('review_speaker_confirm')));
    await tester.pumpAndSettle();
    expect(closed, isTrue);
    expect(_speakerAnswer(sent)['person_id'], 'p-dana');
    expect(_speakerAnswer(sent)['new_person_name'], isNull);
    expect(_speakerAnswer(sent)['is_me'], false);
  });

  testWidgets('optimistic placeholder people never appear in the picker, so their temp ids cannot be sent',
      (tester) async {
    final sent = <(String, Map<String, dynamic>)>[];
    await _pumpSheet(
      tester,
      review: await _review(sent),
      people: [_person('optimistic-person:local-1', 'Draft Person'), _person('p-dana', 'Dana')],
    );
    await _openPicker(tester);
    expect(find.byKey(const Key('speaker_picker_person_optimistic-person:local-1')), findsNothing);
    expect(find.text('Draft Person'), findsNothing);
    expect(find.byKey(const Key('speaker_picker_person_p-dana')), findsOneWidget);
  });

  testWidgets('a broad query stays bounded: at most 24 matches render behind Show all', (tester) async {
    final sent = <(String, Map<String, dynamic>)>[];
    // 30 people all matching the single-character query "a".
    await _pumpSheet(
      tester,
      review: await _review(sent),
      people: [for (var i = 0; i < 30; i++) _person('p-a$i', 'A Person $i')],
    );
    await _openPicker(tester);
    // The query "person" matches all 30 fixture people but neither fixture
    // candidate (Béla, Marcus), so the count below is purely the bounded
    // Everyone tail.
    await tester.enterText(find.byType(OmiSearchField), 'person');
    await tester.pumpAndSettle();

    int personRows() => tester
        .widgetList(find.byWidgetPredicate(
          (w) => w.key is ValueKey<String> && (w.key as ValueKey<String>).value.startsWith('speaker_picker_person_'),
        ))
        .length;
    expect(personRows(), 24);
    expect(find.byKey(const Key('speaker_picker_show_all')), findsOneWidget);

    await tester.ensureVisible(find.byKey(const Key('speaker_picker_show_all')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('speaker_picker_show_all')));
    await tester.pumpAndSettle();
    expect(personRows(), 30);
    expect(find.byKey(const Key('speaker_picker_show_all')), findsNothing);
  });

  testWidgets('typing an existing name offers no new person, so the listed person is what gets sent', (tester) async {
    final sent = <(String, Map<String, dynamic>)>[];
    await _pumpSheet(tester, review: await _review(sent), people: [_person('p-dana', 'Dana')]);
    await _openPicker(tester);
    await tester.enterText(find.byType(OmiSearchField), 'dana');
    await tester.pumpAndSettle();
    // The duplicate guard: no "Add “dana”" row; Dana herself is the only hit.
    expect(find.text('Add “dana”'), findsNothing);
    expect(find.text('New Person…'), findsOneWidget);
    expect(find.byKey(const Key('speaker_picker_person_p-dana')), findsOneWidget);

    await tester.tap(find.byKey(const Key('speaker_picker_person_p-dana')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('review_speaker_confirm')));
    await tester.pumpAndSettle();
    expect(_speakerAnswer(sent)['person_id'], 'p-dana');
    expect(_speakerAnswer(sent)['new_person_name'], isNull);
  });

  testWidgets('the new-person dialog refuses a name that already exists', (tester) async {
    final sent = <(String, Map<String, dynamic>)>[];
    await _pumpSheet(tester, review: await _review(sent), people: [_person('p-dana', 'Dana')]);
    await _openPicker(tester);
    await tester.tap(find.byKey(const Key('speaker_picker_new_person')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('speaker_tag_prompt_name_field')), 'dana');
    await tester.pumpAndSettle();
    expect(find.text('A person with this name already exists.'), findsOneWidget);
    final save = tester.widget<TextButton>(find.byKey(const Key('speaker_tag_prompt_name_save')));
    expect(save.onPressed, isNull);
    await tester.tap(find.byKey(const Key('speaker_tag_prompt_name_save')));
    await tester.pumpAndSettle();
    expect(find.text('Who is this?'), findsOneWidget);
    expect(sent, isEmpty);
  });

  testWidgets('a genuinely new name stages and sends new_person_name', (tester) async {
    final sent = <(String, Map<String, dynamic>)>[];
    await _pumpSheet(tester, review: await _review(sent), people: [_person('p-dana', 'Dana')]);
    await _openPicker(tester);
    await tester.enterText(find.byType(OmiSearchField), 'Zsofia');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Add “Zsofia”'));
    await tester.pumpAndSettle();
    expect(find.text('Confirm Zsofia'), findsOneWidget);

    await tester.tap(find.byKey(const Key('review_speaker_confirm')));
    await tester.pumpAndSettle();
    expect(_speakerAnswer(sent)['new_person_name'], 'Zsofia');
    expect(_speakerAnswer(sent)['person_id'], isNull);
  });

  testWidgets('a typed name that matches a candidate picks that person instead of duplicating them', (tester) async {
    final sent = <(String, Map<String, dynamic>)>[];
    await _pumpSheet(tester, review: await _review(sent), people: [_person('p-dana', 'Dana')]);
    await _openPicker(tester);
    // Riley is a candidate but not in the people list, so the row reads as adding; the guard
    // resolves it to the candidate's person id.
    await tester.enterText(find.byType(OmiSearchField), 'riley');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Add “riley”'));
    await tester.pumpAndSettle();
    expect(find.text('Confirm Riley'), findsOneWidget);

    await tester.tap(find.byKey(const Key('review_speaker_confirm')));
    await tester.pumpAndSettle();
    expect(_speakerAnswer(sent)['person_id'], 'p-riley');
    expect(_speakerAnswer(sent)['new_person_name'], isNull);
  });

  testWidgets('the Me answer is unchanged, and Not Sure answers on a fresh sheet', (tester) async {
    final sent = <(String, Map<String, dynamic>)>[];
    var closed = false;
    await _pumpSheet(
      tester,
      review: await _review(sent),
      people: [_person('p-dana', 'Dana')],
      onDone: () => closed = true,
    );
    await tester.tap(find.text('Me'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('review_speaker_confirm')));
    await tester.pumpAndSettle();
    expect(closed, isTrue);
    expect(_speakerAnswer(sent)['is_me'], true);

    // The first answer took the item off the queue, so Not Sure runs on a fresh sheet.
    await _pumpSheet(tester, review: await _review(sent), people: [_person('p-dana', 'Dana')]);
    await tester.tap(find.text('Not Sure'));
    await tester.pumpAndSettle();
    expect(sent.last.$2['not_sure'], true);
  });

  testWidgets('a candidate chip still quick-answers with that person', (tester) async {
    final sent = <(String, Map<String, dynamic>)>[];
    await _pumpSheet(tester, review: await _review(sent), people: [_person('p-dana', 'Dana')]);
    await tester.tap(find.text('Béla'));
    await tester.pumpAndSettle();
    expect(find.text('Confirm Béla'), findsOneWidget);
    await tester.tap(find.byKey(const Key('review_speaker_confirm')));
    await tester.pumpAndSettle();
    expect(_speakerAnswer(sent)['person_id'], 'p-bela');
  });
}
