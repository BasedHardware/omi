import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';

ServerConversation _conversationWithSections() {
  final structured = Structured('Sprint sync', 'Short compatibility paragraph.', emoji: '🧠');
  structured.sections = [
    const wire.GeneratedSection(heading: 'Decisions', bodyMarkdown: 'Ship the beta on Friday'),
    const wire.GeneratedSection(heading: 'Risks', bodyMarkdown: 'Backend migration is not started yet'),
  ];
  return ServerConversation(id: 'conv-1', createdAt: DateTime.utc(2026, 7, 1), structured: structured);
}

Future<void> _pumpSummary(WidgetTester tester, ServerConversation conversation, AppResponse response) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData.dark(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: CustomScrollView(
          slivers: [
            AppResultDetailWidget(appResponse: response, app: null, conversation: conversation, asSliver: true),
          ],
        ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  group('sectionsToMarkdown', () {
    test('renders each section as a heading followed by its markdown body', () {
      final markdown = sectionsToMarkdown(const [
        wire.GeneratedSection(heading: 'Decisions', bodyMarkdown: '- Ship on Friday'),
        wire.GeneratedSection(heading: 'Risks', bodyMarkdown: 'Migration pending'),
      ]);

      expect(markdown, '## Decisions\n\n- Ship on Friday\n\n## Risks\n\nMigration pending');
    });

    test('skips fully empty sections', () {
      final markdown = sectionsToMarkdown(const [
        wire.GeneratedSection(heading: '  ', bodyMarkdown: ''),
        wire.GeneratedSection(heading: 'Kept', bodyMarkdown: 'Body'),
      ]);

      expect(markdown, '## Kept\n\nBody');
    });
  });

  group('conversation summary sections rendering', () {
    testWidgets('renders section headings and bodies under the overview', (tester) async {
      final conversation = _conversationWithSections();

      await _pumpSummary(tester, conversation, AppResponse(conversation.structured.overview, appId: null));

      expect(find.textContaining('Short compatibility paragraph.', findRichText: true), findsOneWidget);
      expect(find.textContaining('Decisions', findRichText: true), findsOneWidget);
      expect(find.textContaining('Ship the beta on Friday', findRichText: true), findsOneWidget);
      expect(find.textContaining('Risks', findRichText: true), findsOneWidget);
      expect(find.textContaining('Backend migration is not started yet', findRichText: true), findsOneWidget);
    });

    testWidgets('an app-generated summary replaces the structured sections', (tester) async {
      final conversation = _conversationWithSections();

      await _pumpSummary(tester, conversation, AppResponse('App summary', appId: 'app-1'));

      expect(find.textContaining('App summary', findRichText: true), findsOneWidget);
      expect(find.textContaining('Decisions', findRichText: true), findsNothing);
    });
  });
}
