import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  testWidgets('sheet closes while a speaker save is pending and the transcript rolls back on failure', (tester) async {
    final response = Completer<bool>();
    final provider =
        ConversationDetailProvider(assignSpeaker: (_, __, {isUser, personId, speakerId}) => response.future);
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
              end: 1)
        ]);
    provider.selectedDate = conversation.createdAt;
    provider.setCachedConversation(conversation);
    await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => PeopleProvider()),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
              body: Builder(
                  builder: (context) => Column(children: [
                        Consumer<ConversationDetailProvider>(
                            builder: (_, detail, __) =>
                                Text(detail.conversation.transcriptSegments.single.isUser ? 'You' : 'Speaker')),
                        ElevatedButton(
                            onPressed: () => showNameSpeakerSheet(context,
                                    speakerId: 0, segmentId: 'segment', segments: conversation.transcriptSegments,
                                    onSpeakerAssigned: (_, personId, __, ids, ___) async {
                                  final pending = provider.startSpeakerAssignment(ids, personId);
                                  if (pending == null) return false;
                                  unawaited(pending);
                                  return true;
                                }),
                            child: const Text('Open')),
                      ]))),
        )));
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
  testWidgets('name-only suggestion survives initialization; failed save stays open and bulk includes corrections',
      (tester) async {
    final segments = [
      TranscriptSegment(
          id: 'first',
          text: 'First synthetic speech',
          speaker: 'SPEAKER_00',
          isUser: false,
          personId: null,
          start: 0,
          end: 2,
          translations: []),
      TranscriptSegment(
          id: 'wrong',
          text: 'Wrongly assigned speech',
          speaker: 'SPEAKER_00',
          isUser: true,
          personId: null,
          start: 2,
          end: 4,
          translations: []),
    ];
    final calls = <({String name, List<String> ids, bool whole})>[];
    await tester.pumpWidget(ChangeNotifierProvider(
        create: (_) => PeopleProvider(),
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
              body: NameSpeakerBottomSheet(
                  speakerId: 0,
                  segmentId: 'first',
                  segments: segments,
                  suggestion:
                      SpeakerLabelSuggestionEvent(speakerId: 0, personId: '', personName: 'Alex', segmentId: 'first'),
                  onSpeakerAssigned: (speaker, person, name, ids, whole) async {
                    calls.add((name: name, ids: ids, whole: whole));
                    return false;
                  })),
        )));
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
          translations: []),
    ];
    final calls = <({List<String> ids, bool whole})>[];
    await tester.pumpWidget(ChangeNotifierProvider(
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
                  })),
        )));
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
          translations: []),
    ];
    final calls = <bool>[];
    await tester.pumpWidget(ChangeNotifierProvider(
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
                  })),
        )));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byType(OmiButton));
    await tester.tap(find.byType(OmiButton));
    await tester.pumpAndSettle();
    expect(calls.single, isFalse);
  });
}
