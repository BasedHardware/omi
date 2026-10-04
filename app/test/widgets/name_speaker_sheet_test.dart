import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';

Person _person(String id, String name) =>
    Person(id: id, name: name, createdAt: DateTime(2026), updatedAt: DateTime(2026));

TranscriptSegment _seg(String id, {String? personId}) => TranscriptSegment(
      id: id,
      text: 'speech',
      speaker: 'SPEAKER_00',
      isUser: false,
      personId: personId,
      translations: [],
      start: 0,
      end: 1,
    );

Future<void> _pumpSheet(
  WidgetTester tester, {
  required List<Person> people,
  List<TranscriptSegment> segments = const [],
  SpeakerLabelSuggestionEvent? suggestion,
  Future<bool> Function(
    int speakerId,
    String personId,
    String personName,
    List<String> segmentIds,
    bool applyToSpeaker,
  )? onSpeakerAssigned,
}) async {
  final provider = PeopleProvider()..people = people;
  await tester.pumpWidget(
    ChangeNotifierProvider.value(
      value: provider,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: NameSpeakerBottomSheet(
            speakerId: 0,
            segmentId: 'seg0',
            segments: [_seg('seg0'), ...segments],
            suggestion: suggestion,
            onSpeakerAssigned: onSpeakerAssigned ?? (_, __, ___, ____, _____) async => false,
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

List<String> _chipNames(WidgetTester tester) =>
    tester.widgetList<OmiFilterChip>(find.byType(OmiFilterChip)).map((c) => c.label).toList();

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  testWidgets('Someone else excludes the rejected near match and requires an explicit choice', (tester) async {
    final assignments = <String>[];
    await _pumpSheet(
      tester,
      people: [_person('maya', 'Maya'), _person('sam', 'Sam')],
      suggestion: SpeakerLabelSuggestionEvent(
        speakerId: 0,
        personId: '',
        personName: 'Maya',
        segmentId: 'seg0',
        suggestedPersonId: 'maya',
      ),
      onSpeakerAssigned: (_, id, __, ___, ____) async {
        assignments.add(id);
        return false;
      },
    );
    expect(_chipNames(tester), contains('Sam'));
    expect(_chipNames(tester), isNot(contains('Maya')));
    expect(find.byType(TextField), findsNothing);
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(assignments, isEmpty);
    await tester.tap(find.text('Sam'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(assignments, ['sam']);
  });

  testWidgets('sheet closes while a speaker save is pending and the transcript rolls back on failure', (tester) async {
    final response = Completer<bool>();
    final provider = ConversationDetailProvider(
      assignSpeaker: (_, __, {isUser, personId, speakerId}) => response.future,
    );
    final conversation = ServerConversation(
      id: 'conversation',
      createdAt: DateTime(2026),
      structured: Structured('Title', ''),
      transcriptSegments: [
        TranscriptSegment(
          id: 'segment',
          text: 'Hello',
          speaker: 'SPEAKER_00',
          isUser: false,
          personId: null,
          translations: [],
          start: 0,
          end: 1,
        ),
      ],
    );
    provider.selectedDate = conversation.createdAt;
    provider.setCachedConversation(conversation);
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => PeopleProvider()),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: Builder(
              builder: (context) => Column(
                children: [
                  Consumer<ConversationDetailProvider>(
                    builder: (_, detail, __) =>
                        Text(detail.conversation.transcriptSegments.single.isUser ? 'You' : 'Speaker'),
                  ),
                  ElevatedButton(
                    onPressed: () => showNameSpeakerSheet(
                      context,
                      speakerId: 0,
                      segmentId: 'segment',
                      segments: conversation.transcriptSegments,
                      onSpeakerAssigned: (_, personId, __, ids, ___) async {
                        final pending = provider.startSpeakerAssignment(ids, personId);
                        if (pending == null) return false;
                        unawaited(pending);
                        return true;
                      },
                    ),
                    child: const Text('Open'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byType(OmiButton));
    await tester.tap(find.byType(OmiButton));
    await tester.pumpAndSettle();
    expect(find.text('You'), findsOneWidget);
    expect(find.byType(NameSpeakerBottomSheet), findsNothing);
    response.complete(false);
    await tester.pumpAndSettle();
    expect(find.text('Speaker'), findsOneWidget);
    provider.dispose();
  });
  testWidgets('name-only suggestion survives initialization; failed save stays open and bulk includes corrections', (
    tester,
  ) async {
    final segments = [
      TranscriptSegment(
        id: 'first',
        text: 'First synthetic speech',
        speaker: 'SPEAKER_00',
        isUser: false,
        personId: null,
        start: 0,
        end: 2,
        translations: [],
      ),
      TranscriptSegment(
        id: 'wrong',
        text: 'Wrongly assigned speech',
        speaker: 'SPEAKER_00',
        isUser: true,
        personId: null,
        start: 2,
        end: 4,
        translations: [],
      ),
    ];
    final calls = <({String name, List<String> ids, bool whole})>[];
    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => PeopleProvider(),
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: NameSpeakerBottomSheet(
              speakerId: 0,
              segmentId: 'first',
              segments: segments,
              suggestion: SpeakerLabelSuggestionEvent(
                speakerId: 0,
                personId: '',
                personName: 'Alex',
                segmentId: 'first',
              ),
              onSpeakerAssigned: (speaker, person, name, ids, whole) async {
                calls.add((name: name, ids: ids, whole: whole));
                return false;
              },
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Alex'), findsOneWidget);
    final save = find.byType(OmiButton);
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(calls.single.name, 'Alex');
    expect(calls.single.ids, ['first']);
    expect(calls.single.whole, isFalse);
    expect(find.byType(NameSpeakerBottomSheet), findsOneWidget);
    final bulk = find.byType(CheckboxListTile).first;
    await tester.ensureVisible(bulk);
    await tester.tap(bulk);
    await tester.pumpAndSettle();
    expect(find.textContaining('Wrongly assigned speech'), findsOneWidget);
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(calls.last.ids, ['first', 'wrong']);
    expect(calls.last.whole, isTrue);
  });

  testWidgets('unresolved speakers title reads "Name Speaker" instead of the dense tag number', (tester) async {
    Future<void> open({required bool unresolvedSpeakers}) async {
      await tester.pumpWidget(
        ChangeNotifierProvider(
          create: (_) => PeopleProvider(),
          child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Scaffold(
              body: Builder(
                builder: (context) => ElevatedButton(
                  onPressed: () => showNameSpeakerSheet(
                    context,
                    speakerId: 0,
                    segmentId: 'only',
                    segments: [
                      TranscriptSegment(
                        id: 'only',
                        text: 'Only synthetic speech',
                        speaker: 'SPEAKER_00',
                        isUser: false,
                        personId: null,
                        start: 0,
                        end: 2,
                        translations: [],
                      ),
                    ],
                    unresolvedSpeakers: unresolvedSpeakers,
                    onSpeakerAssigned: (_, __, ___, ____, _____) async => true,
                  ),
                  child: const Text('Open'),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
    }

    await open(unresolvedSpeakers: true);
    expect(find.text('Name Speaker'), findsOneWidget);
    expect(find.text('Tag Speaker 1'), findsNothing);
    await tester.tap(find.byType(OmiCloseButton));
    await tester.pumpAndSettle();

    await open(unresolvedSpeakers: false);
    expect(find.text('Tag Speaker 1'), findsOneWidget);
    await tester.tap(find.byType(OmiCloseButton));
    await tester.pumpAndSettle();
  });

  testWidgets('live default tags a single in-progress bubble as speaker-wide including later speech', (tester) async {
    final segments = [
      TranscriptSegment(
        id: 'only',
        text: 'Only synthetic speech',
        speaker: 'SPEAKER_00',
        isUser: false,
        personId: null,
        start: 0,
        end: 2,
        translations: [],
      ),
    ];
    final calls = <({List<String> ids, bool whole})>[];
    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => PeopleProvider(),
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: NameSpeakerBottomSheet(
              speakerId: 0,
              segmentId: 'only',
              segments: segments,
              defaultApplyToSpeaker: true,
              onSpeakerAssigned: (speaker, person, name, ids, whole) async {
                calls.add((ids: ids, whole: whole));
                return true;
              },
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('later speech'), findsOneWidget);
    final checkbox = tester.widget<CheckboxListTile>(find.byType(CheckboxListTile).first);
    expect(checkbox.value, isTrue);
    expect(checkbox.onChanged, isNotNull);
    await tester.ensureVisible(find.byType(OmiButton));
    await tester.tap(find.byType(OmiButton));
    await tester.pumpAndSettle();
    expect(calls.single.ids, ['only']);
    expect(calls.single.whole, isTrue);
  });

  testWidgets('detail default with one bubble stays a selected-segments edit', (tester) async {
    final segments = [
      TranscriptSegment(
        id: 'only',
        text: 'Only synthetic speech',
        speaker: 'SPEAKER_00',
        isUser: false,
        personId: null,
        start: 0,
        end: 2,
        translations: [],
      ),
    ];
    final calls = <bool>[];
    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => PeopleProvider(),
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: NameSpeakerBottomSheet(
              speakerId: 0,
              segmentId: 'only',
              segments: segments,
              onSpeakerAssigned: (speaker, person, name, ids, whole) async {
                calls.add(whole);
                return true;
              },
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byType(OmiButton));
    await tester.tap(find.byType(OmiButton));
    await tester.pumpAndSettle();
    expect(calls.single, isFalse);
  });

  testWidgets('search field appears above the threshold and filters chips case- and diacritic-insensitively', (
    tester,
  ) async {
    SharedPreferencesUtil().givenName = 'Owner';
    final people = [
      _person('p1', 'Alex'),
      _person('p2', 'Alicia'),
      _person('p3', 'Alice'),
      _person('p4', 'Bob'),
      _person('p5', 'Carol'),
      _person('p6', 'Dave'),
      _person('p7', 'Erin'),
      _person('p8', 'Frank'),
      _person('p9', 'Grace'),
      _person('p10', 'Heidi'),
      _person('p11', 'Ivan'),
      _person('p12', 'José'),
    ];
    await _pumpSheet(tester, people: people);

    expect(find.byType(TextField), findsOneWidget);
    // "+ Add Person" and "You" are present before searching.
    expect(find.text('Add Person'), findsOneWidget);
    expect(find.text('You'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'AL');
    await tester.pumpAndSettle();
    expect(_chipNames(tester), ['Add Person', 'You', 'Alex', 'Alice', 'Alicia']);
    expect(find.text('Bob'), findsNothing);

    // Diacritic-insensitive: "jose" matches "José".
    await tester.enterText(find.byType(TextField), 'jose');
    await tester.pumpAndSettle();
    expect(_chipNames(tester), ['Add Person', 'You', 'José']);

    // Clearing the query restores the full grid.
    await tester.enterText(find.byType(TextField), '');
    await tester.pumpAndSettle();
    expect(_chipNames(tester).length, 14); // Add + You + 12 people.
  });

  testWidgets('search field stays hidden at or below the threshold', (tester) async {
    SharedPreferencesUtil().givenName = 'Owner';
    final people = List.generate(10, (i) => _person('p$i', 'Person ${i.toString().padLeft(2, '0')}'));
    await _pumpSheet(tester, people: people);
    expect(find.byType(TextField), findsNothing);
    expect(_chipNames(tester).length, 12); // Add + You + 10 people.
  });

  testWidgets('no search match offers the query as a new person with the shared validation', (tester) async {
    SharedPreferencesUtil().givenName = 'Owner';
    final people = List.generate(11, (i) => _person('p$i', 'Person ${i.toString().padLeft(2, '0')}'));
    final calls = <String>[];
    await _pumpSheet(
      tester,
      people: people,
      onSpeakerAssigned: (_, __, name, ___, ____) async {
        calls.add(name);
        return true;
      },
    );

    await tester.enterText(find.byType(TextField), 'Zed');
    await tester.pumpAndSettle();
    // Only "+ Add Person" and "You" remain, plus the inline add row.
    expect(_chipNames(tester), ['Add Person', 'You']);
    final addRow = find.text('Add "Zed" as a new person');
    expect(addRow, findsOneWidget);

    await tester.tap(addRow);
    await tester.pumpAndSettle();
    expect(find.text('Zed'), findsOneWidget); // Prefilled new-person input.
    expect(find.text('Enter Person\'s Name'), findsOneWidget);

    final save = find.byType(OmiButton);
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(calls.single, 'Zed');
  });

  testWidgets('adding the own name from the no-match row keeps the save disabled', (tester) async {
    SharedPreferencesUtil().givenName = 'Owner';
    final people = List.generate(11, (i) => _person('p$i', 'Person ${i.toString().padLeft(2, '0')}'));
    await _pumpSheet(tester, people: people);

    await tester.enterText(find.byType(TextField), 'Owner');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Add "Owner" as a new person'));
    await tester.pumpAndSettle();
    expect(find.text('To tag yourself, please select "You" from the list.'), findsOneWidget);
    expect(tester.widget<OmiButton>(find.byType(OmiButton)).onPressed, isNull);
  });

  testWidgets('recency reorders people between "You" and in-conversation frequency', (tester) async {
    SharedPreferencesUtil().givenName = 'Owner';
    final now = DateTime.now().millisecondsSinceEpoch;
    SharedPreferencesUtil().speakerLabelLastUsedMs = {'p3': now - 1000, 'p2': now};
    await _pumpSheet(
      tester,
      people: [_person('p1', 'Alice'), _person('p2', 'Bob'), _person('p3', 'Carol')],
      segments: [
        _seg('s1', personId: 'p1'),
        _seg('s2', personId: 'p1'),
        _seg('s3', personId: 'p1'),
        _seg('s4', personId: 'p2'),
        _seg('s5', personId: 'p3'),
        _seg('s6', personId: 'p3'),
      ],
    );
    // "You" first, then most-recently-used (Bob > Carol), then frequency
    // (Alice has 3 segments but no recency).
    expect(_chipNames(tester), ['Add Person', 'You', 'Bob', 'Carol', 'Alice']);
  });

  testWidgets('grid is capped and a "Show all" chip expands it inline', (tester) async {
    SharedPreferencesUtil().givenName = 'Owner';
    final people = List.generate(26, (i) => _person('p${i + 1}', 'Person ${(i + 1).toString().padLeft(2, '0')}'));
    await _pumpSheet(tester, people: people);

    // Add + "You" + first 24 people + expander.
    expect(_chipNames(tester).length, 27);
    expect(find.text('Person 24'), findsOneWidget);
    expect(find.text('Person 25'), findsNothing);
    expect(find.text('Show all 26 people'), findsOneWidget);

    await tester.ensureVisible(find.text('Show all 26 people'));
    await tester.tap(find.text('Show all 26 people'));
    await tester.pumpAndSettle();
    expect(_chipNames(tester).length, 28); // Add + "You" + all 26 people.
    expect(find.text('Person 26'), findsOneWidget);
    expect(find.text('Show all 26 people'), findsNothing);
  });

  testWidgets('searching shows every match without the cap', (tester) async {
    SharedPreferencesUtil().givenName = 'Owner';
    final people = List.generate(26, (i) => _person('p${i + 1}', 'Person ${(i + 1).toString().padLeft(2, '0')}'));
    await _pumpSheet(tester, people: people);

    await tester.enterText(find.byType(TextField), 'Person 2');
    await tester.pumpAndSettle();
    // Person 20..26 all match; no cap, no expander while searching.
    expect(_chipNames(tester), [
      'Add Person',
      'You',
      ...List.generate(7, (i) => 'Person ${(20 + i).toString().padLeft(2, '0')}'),
    ]);
    expect(find.text('Show all 26 people'), findsNothing);
  });

  testWidgets('successful save records speaker label recency', (tester) async {
    SharedPreferencesUtil().givenName = 'Owner';
    await _pumpSheet(
      tester,
      people: [_person('p1', 'Alice'), _person('p3', 'Carol')],
      onSpeakerAssigned: (_, personId, __, ___, ____) async {
        return personId == 'p3';
      },
    );

    await tester.ensureVisible(find.text('Carol'));
    await tester.tap(find.text('Carol'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byType(OmiButton));
    await tester.tap(find.byType(OmiButton));
    await tester.pumpAndSettle();

    final lastUsed = SharedPreferencesUtil().speakerLabelLastUsedMs;
    expect(lastUsed.containsKey('p3'), isTrue);
    expect(lastUsed['p3'], greaterThan(0));
  });

  testWidgets('failed save does not record speaker label recency', (tester) async {
    SharedPreferencesUtil().givenName = 'Owner';
    await _pumpSheet(
      tester,
      people: [_person('p1', 'Alice'), _person('p3', 'Carol')],
      onSpeakerAssigned: (_, __, ___, ____, _____) async => false,
    );

    await tester.ensureVisible(find.text('Carol'));
    await tester.tap(find.text('Carol'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byType(OmiButton));
    await tester.tap(find.byType(OmiButton));
    await tester.pumpAndSettle();

    expect(SharedPreferencesUtil().speakerLabelLastUsedMs, isEmpty);
    expect(find.byType(NameSpeakerBottomSheet), findsOneWidget);
  });
}
