import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_header.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/ui/format/omi_date_format.dart';
import 'package:omi/ui/ui.dart';

class _TitlePersistenceSpy extends ConversationDetailProvider {
  final savedTitles = <String>[];

  @override
  Future<bool> persistTitleEdit(String conversationId, String title) async {
    savedTitles.add(title);
    return true;
  }
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  for (final initialTitle in ['Short title', '']) {
    testWidgets('detail title layout and recording fallback: $initialTitle', (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);

      final conversation = ServerConversation(
        id: 'title-alignment',
        createdAt: DateTime(2026, 9, 28, 12),
        structured: Structured(initialTitle, '', emoji: '🧠'),
      );
      final detail = _TitlePersistenceSpy()
        ..selectedDate = conversationLocalDayKey(conversation.createdAt)
        ..setCachedConversation(conversation)
        ..titleController = TextEditingController(text: conversation.structured.title)
        ..titleFocusNode = FocusNode();
      final folders = FolderProvider(foldersFetcher: () async => []);
      addTearDown(detail.dispose);
      addTearDown(folders.dispose);

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
            ChangeNotifierProvider<FolderProvider>.value(value: folders),
          ],
          child: MaterialApp(
            theme: buildOmiTheme(),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Scaffold(body: ConversationDetailHeader(onOpenRecordings: (_) {})),
          ),
        ),
      );

      final titleField = find.byType(ConversationTitleField);
      const lineHeight = 28.0 * 1.15; // OmiType.title1 with the header's line height.

      void expectLines(int lines) {
        expect(tester.getSize(titleField).height, closeTo(lineHeight * lines, 1));
      }

      expect(find.text('🧠'), findsNothing);
      expectLines(1);
      if (initialTitle.isEmpty) {
        expect(
          find.text(OmiDateFormat.of(tester.element(titleField)).dateTime(conversation.createdAt.toLocal())),
          findsOneWidget,
        );
        expect(find.text('Untitled Conversation'), findsNothing);
        expect(detail.titleController!.text, isEmpty);
        expect(conversation.structured.title, isEmpty);
      }

      // Rename without an edit must never persist the displayed date placeholder.
      await tester.tap(titleField);
      await tester.pump();
      expect(detail.titleFocusNode!.hasFocus, isTrue);
      detail.titleFocusNode!.unfocus();
      await tester.pump();
      expect(detail.savedTitles, isEmpty);
      expect(detail.titleController!.text, initialTitle);
      expect(conversation.structured.title, initialTitle);

      detail.titleController!.text = 'First line\nSecond line';
      await tester.pump();
      expectLines(2);

      detail.titleController!.text = 'One\nTwo\nThree\nFour';
      await tester.pump();
      expectLines(3);
    });
  }

  testWidgets('a legacy title shows repaired at rest but edits from the stored title', (tester) async {
    final conversation = ServerConversation(
      id: 'title-citations',
      createdAt: DateTime(2026, 9, 28, 12),
      structured: Structured('Kickoff [s01234]', ''),
      transcriptSegments: [
        TranscriptSegment(
            id: 's01234', text: 'Hi', speaker: null, isUser: false, personId: null, start: 0, end: 1, translations: []),
      ],
    );
    final detail = _TitlePersistenceSpy()
      ..selectedDate = conversationLocalDayKey(conversation.createdAt)
      ..setCachedConversation(conversation)
      ..titleController = TextEditingController(text: conversation.structured.title)
      ..titleFocusNode = FocusNode();
    final folders = FolderProvider(foldersFetcher: () async => []);
    addTearDown(detail.dispose);
    addTearDown(folders.dispose);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
          ChangeNotifierProvider<FolderProvider>.value(value: folders),
        ],
        child: MaterialApp(
          theme: buildOmiTheme(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: ConversationDetailHeader(onOpenRecordings: (_) {})),
        ),
      ),
    );

    final atRest = tester.widget<Text>(find.byKey(const Key('conversation_title_at_rest')));
    expect(atRest.data, 'Kickoff');
    await tester.tap(find.byType(ConversationTitleField));
    await tester.pump();
    expect(detail.titleController!.text, 'Kickoff [s01234]');
    detail.titleFocusNode!.unfocus();
    await tester.pump();
    expect(detail.savedTitles, isEmpty, reason: 'an untouched title is never saved, repaired or not');
    expect(conversation.structured.title, 'Kickoff [s01234]');
  });

  testWidgets('a title that was only debris reads as untitled at rest, never as the debris', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildOmiTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: ConversationTitleField(
            style: const TextStyle(fontSize: 20),
            controller: TextEditingController(text: '[s01234]'),
            focusNode: FocusNode(),
            hintText: 'Recording at noon',
            displayText: (stored) => '',
          ),
        ),
      ),
    );
    final atRest = tester.widget<Text>(find.byKey(const Key('conversation_title_at_rest')));
    expect(atRest.data, 'Recording at noon');
  });
}
