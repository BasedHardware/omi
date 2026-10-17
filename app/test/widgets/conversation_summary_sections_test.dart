import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/utils/audio/conversation_playback_controller.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_summary_selection.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/providers/conversation_provider.dart';

ServerConversation _conversationWithSections(
    {List<AppResponse> appResults = const [],
    String overview = '',
    List<TranscriptSegment> transcriptSegments = const []}) {
  final structured = Structured('Sprint sync', overview, emoji: '🧠');
  structured.sections = [
    const wire.GeneratedSection(heading: 'Decisions', bodyMarkdown: 'Ship the beta on Friday'),
    const wire.GeneratedSection(heading: 'Risks', bodyMarkdown: 'Backend migration is not started yet'),
  ];
  return ServerConversation(
    id: 'conv-1',
    createdAt: DateTime(2026, 7, 1, 9).toUtc(),
    structured: structured,
    appResults: appResults,
    transcriptSegments: transcriptSegments,
  );
}

Future<void> _pumpSummary(
  WidgetTester tester,
  ServerConversation conversation, {
  bool asSliver = true,
  ValueChanged<String>? onOpenSource,
  void Function(ConversationSummarySelection selection, String newContent)? onSaveSummarySelection,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData.dark(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: asSliver
            ? CustomScrollView(
                slivers: [
                  AppResultDetailWidget(
                    summarySelection: ConversationSummarySelection.select(conversation),
                    app: null,
                    conversation: conversation,
                    onSaveSummarySelection: onSaveSummarySelection,
                    asSliver: true,
                    onOpenSource: onOpenSource,
                  ),
                ],
              )
            : AppResultDetailWidget(
                summarySelection: ConversationSummarySelection.select(conversation),
                app: null,
                conversation: conversation,
                onSaveSummarySelection: onSaveSummarySelection,
              ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  testWidgets('typed section chips navigate and highlight through the existing transcript controller', (tester) async {
    final conversation = _conversationWithSections(transcriptSegments: [
      TranscriptSegment(
          id: 's1', text: 'Approved', speaker: null, isUser: false, personId: null, start: 3, end: 5, translations: [])
    ]);
    conversation.structured.sections = [
      const Section(heading: 'Decision []', bodyMarkdown: 'Approved. [s1]', sourceSegmentIds: ['missing', 's1', 's1']),
      const Section(heading: 'Legacy', bodyMarkdown: 'No typed sources. [s1] []'),
    ];
    final selection = ConversationSummarySelection.select(conversation);
    expect(selection.sections[0].sourceSegmentIds, ['s1']);
    expect(selection.sections[1].sourceSegmentIds, isEmpty);
    final controller = ConversationPlaybackController(segments: conversation.transcriptSegments);
    addTearDown(controller.dispose);
    await _pumpSummary(tester, conversation, onOpenSource: (id) {
      final segment = conversation.transcriptSegments.singleWhere((segment) => segment.id == id);
      controller.seek(segment.start, strict: true);
    });
    expect(find.byKey(const ValueKey('note-source-0-0')), findsOneWidget);
    expect(find.byKey(const ValueKey('note-source-1-0')), findsNothing);
    await tester.tap(find.byKey(const ValueKey('note-source-0-0')));
    await tester.pump();
    expect(controller.highlightedSegment.value, 's1');
    expect(controller.followTargetSegmentId, 's1');
    expect(controller.followRequest, 1);
    expect(controller.isPlaying, isFalse);
    expect(conversation.structured.sections.first.heading, 'Decision []');
  });

  testWidgets('section presentation still edits the entire selected summary', (tester) async {
    final conversation = _conversationWithSections();
    await _pumpSummary(tester, conversation, onSaveSummarySelection: (_, __) {});
    final body = find.textContaining('Ship the beta on Friday', findRichText: true);
    await tester.tap(body);
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(body);
    await tester.pump();
    expect(find.byType(TextField), findsOneWidget);
    final editor = tester.widget<TextField>(find.byType(TextField));
    expect(editor.controller!.text, ConversationSummarySelection.select(conversation).content);
    expect(editor.controller!.text, contains('Risks'));
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 1));
  });

  group('renderSections', () {
    test('renders each section as a heading followed by its markdown body', () {
      final markdown = ConversationSummarySelection.renderSections(const [
        wire.GeneratedSection(heading: 'Decisions', bodyMarkdown: '- Ship on Friday'),
        wire.GeneratedSection(heading: 'Risks', bodyMarkdown: 'Migration pending'),
      ]);

      expect(markdown, '## Decisions\n\n- Ship on Friday\n\n## Risks\n\nMigration pending');
    });

    test('skips fully empty sections', () {
      final markdown = ConversationSummarySelection.renderSections(const [
        wire.GeneratedSection(heading: '  ', bodyMarkdown: ''),
        wire.GeneratedSection(heading: 'Kept', bodyMarkdown: 'Body'),
      ]);

      expect(markdown, '## Kept\n\nBody');
    });

    test('ignores heading-only sections and keeps body-only sections', () {
      final markdown = ConversationSummarySelection.renderSections(const [
        wire.GeneratedSection(heading: 'Unused', bodyMarkdown: ' '),
        wire.GeneratedSection(heading: '', bodyMarkdown: 'Body only'),
      ]);

      expect(markdown, 'Body only');
    });
  });

  group('conversation summary sections rendering', () {
    testWidgets('renders the projected overview once when it duplicates sections', (tester) async {
      final conversation = _conversationWithSections();
      conversation.structured.overview = ConversationSummarySelection.renderSections(conversation.structured.sections);

      await _pumpSummary(tester, conversation);

      expect(find.textContaining('Decisions', findRichText: true), findsOneWidget);
      expect(find.textContaining('Ship the beta on Friday', findRichText: true), findsOneWidget);
      expect(find.textContaining('Risks', findRichText: true), findsOneWidget);
      expect(find.textContaining('Backend migration is not started yet', findRichText: true), findsOneWidget);
    });

    testWidgets('regular rendering also mounts the selected body once', (tester) async {
      final conversation = _conversationWithSections();
      conversation.structured.overview = ConversationSummarySelection.renderSections(conversation.structured.sections);

      await _pumpSummary(tester, conversation, asSliver: false);

      expect(find.textContaining('Decisions', findRichText: true), findsOneWidget);
      expect(find.textContaining('Ship the beta on Friday', findRichText: true), findsOneWidget);
      expect(find.textContaining('Risks', findRichText: true), findsOneWidget);
      expect(find.textContaining('Backend migration is not started yet', findRichText: true), findsOneWidget);
    });

    testWidgets('an app-generated summary replaces the structured sections', (tester) async {
      final conversation = _conversationWithSections(appResults: [AppResponse('App summary', appId: 'app-1')]);

      await _pumpSummary(tester, conversation);

      expect(find.textContaining('App summary', findRichText: true), findsOneWidget);
      expect(find.textContaining('Decisions', findRichText: true), findsNothing);
    });

    testWidgets('an app result with empty content falls back to the overview or sections once', (tester) async {
      // End of the regression this pane actually showed: the provider handed
      // over an empty-content app result, its non-null appId suppressed the
      // sections, and the empty content selected the "no summary" placeholder.
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();

      final conversation = _conversationWithSections(
        overview: '',
        appResults: [AppResponse('', appId: 'app-1')],
      );

      final provider = ConversationDetailProvider();
      addTearDown(provider.dispose);
      provider.selectedDate = conversationLocalDayKey(conversation.createdAt);
      provider.setCachedConversation(conversation);

      await _pumpSummary(tester, conversation);

      expect(find.textContaining('Decisions', findRichText: true), findsOneWidget);
      expect(find.textContaining('Ship the beta on Friday', findRichText: true), findsOneWidget);
      expect(find.textContaining('No summary available for this app', findRichText: true), findsNothing);
    });

    testWidgets('duplicate app ids disable editing in regular and sliver rendering', (tester) async {
      final conversation = _conversationWithSections(
        appResults: [
          AppResponse('First app summary', appId: 'duplicate'),
          AppResponse('Second app summary', appId: 'duplicate'),
        ],
      );
      var saveCalls = 0;
      void onSave(ConversationSummarySelection selection, String newContent) {
        saveCalls++;
      }

      await _pumpSummary(tester, conversation, onSaveSummarySelection: onSave);
      final summaryFinder = find.textContaining('First app summary', findRichText: true);
      await tester.tap(summaryFinder);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(summaryFinder);
      await tester.pump();
      expect(find.byType(TextField), findsNothing);

      await _pumpSummary(tester, conversation, asSliver: false, onSaveSummarySelection: onSave);
      await tester.tap(summaryFinder);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(summaryFinder);
      await tester.pump();
      expect(find.byType(TextField), findsNothing);
      expect(saveCalls, 0);
    });
  });
}
